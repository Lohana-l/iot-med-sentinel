"""
Orchestration au niveau de la flotte : génère un ensemble de sites × frigos,
les fait avancer dans le temps et émet des événements de télémétrie.

Conçu pour fonctionner :
  • en temps réel, en poussant vers Redpanda toutes les `tick_seconds`
  • en batch, en émettant N heures de télémétrie pour CI / tests hors ligne
"""
from __future__ import annotations

import random
import time
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime

from simulator.model import FridgePhysics, FridgeState


@dataclass
class Fridge:
    fridge_id: str
    site_id:   str
    current_c: float = 5.0
    state:     FridgeState = FridgeState.OK
    state_until_ts: float = 0.0    # epoch secondes ; quand on revient à OK
    physics:   FridgePhysics = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.physics is None:
            self.physics = FridgePhysics()


def make_site_id(index: int) -> str:
    """Identifiant canonique d'un site. Source unique de vérité du format :
    le seed des référentiels (scripts/seed_dimensions.py) réutilise cette
    fonction pour que dimensions et télémétrie restent alignées."""
    return f"SITE-{index:02d}"


def make_fridge_id(site_id: str, index: int) -> str:
    """Identifiant canonique d'un réfrigérateur au sein d'un site."""
    return f"{site_id}-F{index:02d}"


def _init_fleet(
    n_sites: int, fridges_per_site: int, rng: random.Random
) -> list[Fridge]:
    fridges: list[Fridge] = []
    for s in range(n_sites):
        site_id = make_site_id(s)
        for f in range(fridges_per_site):
            fridges.append(
                Fridge(
                    fridge_id=make_fridge_id(site_id, f),
                    site_id=site_id,
                    current_c=rng.uniform(3.5, 6.5),
                )
            )
    return fridges


def _maybe_schedule_event(
    fridge: Fridge, now: float, rng: random.Random, scripted_incident: dict | None
) -> None:
    """Génération probabiliste d'événements + incident scripté optionnel."""

    # l'incident de démo scripté a la priorité : à t0, injecte une panne
    # compresseur de ~5 heures sur un frigo spécifique.
    if (
        scripted_incident
        and not getattr(fridge, "_scripted_done", False)
        and fridge.fridge_id == scripted_incident["fridge_id"]
        and now >= scripted_incident["start_epoch"]
    ):
        fridge.state = FridgeState.COMPRESSOR_FAIL
        fridge.state_until_ts = now + scripted_incident["duration_sec"]
        fridge._scripted_done = True  # type: ignore[attr-defined]
        return

    if fridge.state != FridgeState.OK:
        if now >= fridge.state_until_ts:
            fridge.state = FridgeState.OK
        return

    # Fréquences de fond (par tick @ 30 s) :
    # • ouverture porte : ~4×/j usage clinique, soit p≈0.0014
    # • panne compresseur : MTBF ~7 ans, soit p≈1.4e-7 par 30 s par frigo
    # • micro-coupure : événements locaux rares, soit p≈1e-6 par 30 s
    r = rng.random()
    if r < 0.0014:
        fridge.state = FridgeState.DOOR_OPEN
        fridge.state_until_ts = now + rng.uniform(20, 90)
    elif r < 0.0014 + 1.4e-7:
        fridge.state = FridgeState.COMPRESSOR_FAIL
        fridge.state_until_ts = now + rng.uniform(2 * 3600, 6 * 3600)
    elif r < 0.0014 + 1.4e-7 + 1e-6:
        fridge.state = FridgeState.POWER_GLITCH
        fridge.state_until_ts = now + rng.uniform(180, 600)


def tick(fridges: list[Fridge], now: float, dt_sec: float, rng: random.Random,
         scripted_incident: dict | None) -> list[dict]:
    """Avance chaque frigo de dt_sec et retourne un événement de télémétrie par frigo."""
    events = []
    ts = datetime.fromtimestamp(now, tz=UTC).isoformat()
    for f in fridges:
        _maybe_schedule_event(f, now, rng, scripted_incident)
        f.current_c = f.physics.step(f.current_c, f.state, dt_sec, rng)

        events.append({
            "event_id":      str(uuid.uuid4()),
            "event_ts":      ts,
            "fridge_id":     f.fridge_id,
            "site_id":       f.site_id,
            "temperature_c": round(f.current_c, 2),
            "humidity_pct":  round(max(30.0, min(70.0, 55.0 + rng.gauss(0, 3))), 2),
            "door_open":     f.state == FridgeState.DOOR_OPEN,
            "state":         f.state.value,
        })
    return events


def stream_events(
    *,
    n_sites: int,
    fridges_per_site: int,
    tick_seconds: int,
    hours: float | None = None,
    seed: int = 42,
    realtime: bool = True,
    scripted_incident: dict | None = None,
) -> Iterator[list[dict]]:
    """Génère des batches d'événements de télémétrie.

    Paramètres
    ----------
    realtime : si True, dort entre les ticks ; si False, émet aussi vite que possible
               (utile pour CI / backfills historiques).
    hours    : si renseigné, s'arrête après ce nombre d'heures simulées ; sinon stream indéfiniment.
    """
    rng = random.Random(seed)
    fridges = _init_fleet(n_sites, fridges_per_site, rng)

    start = time.time()
    sim_now = start
    end = None if hours is None else start + hours * 3600

    while end is None or sim_now < end:
        batch = tick(fridges, sim_now, tick_seconds, rng, scripted_incident)
        yield batch
        sim_now += tick_seconds
        if realtime:
            time.sleep(tick_seconds)


def scripted_demo_incident(start_offset_sec: int = 60) -> dict:
    """Injecte une panne compresseur de 5 heures sur SITE-00-F02, une minute après le démarrage.

    Utilisé en CI + dans la boucle de démo live pour que l'histoire se déroule à la demande.
    """
    return {
        "fridge_id": "SITE-00-F02",
        "start_epoch": time.time() + start_offset_sec,
        "duration_sec": 5 * 3600,
    }
