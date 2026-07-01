"""
Modèle physique d'un réfrigérateur pharmaceutique.

Les distributions sont fondées sur :
  • Spécifications techniques OMS pour les réfrigérateurs pharmaceutiques
    (WHO/IVB/2014), Annexe B : plage de fonctionnement normale, temps de maintien
    après coupure électrique, fréquence d'ouverture en milieu clinique.
  • Catalogue PQS E003/RF05 : chiffres MTBF des compresseurs (MTBF terrain moyen
    ~7 ans pour les frigos de classe A).

Tout est déterministe pour une graine aléatoire donnée, de sorte qu'un
incident de démo peut être reproduit à l'identique.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass
from enum import Enum


class FridgeState(str, Enum):
    OK = "ok"
    DOOR_OPEN = "door_open"
    COMPRESSOR_FAIL = "compressor_fail"
    POWER_GLITCH = "power_glitch"


@dataclass
class FridgePhysics:
    """Modèle thermique simple à décroissance exponentielle autour de la consigne."""

    setpoint_c:     float = 5.0                  # point de consigne typique
    ambient_c:      float = 22.0                 # température ambiante
    tau_ok_sec:     float = 180.0                # constante de temps pendant fonctionnement normal
    tau_door_sec:   float = 1200.0               # chauffe vite avec la porte ouverte
    tau_fail_sec:   float = 3600.0               # chauffe lentement en panne compresseur
    noise_c:        float = 0.15

    def step(
        self,
        current_c: float,
        state: FridgeState,
        dt_sec: float,
        rng: random.Random,
    ) -> float:
        """Un pas d'Euler ; système du 1er ordre vers une cible mobile."""
        if state == FridgeState.OK:
            target, tau = self.setpoint_c, self.tau_ok_sec
        elif state == FridgeState.DOOR_OPEN:
            target, tau = self.ambient_c, self.tau_door_sec
        elif state == FridgeState.COMPRESSOR_FAIL:
            target, tau = self.ambient_c, self.tau_fail_sec
        else:  # POWER_GLITCH : légère montée puis rétablissement
            target, tau = self.ambient_c, self.tau_fail_sec * 2.0

        next_c = current_c + (target - current_c) * (1.0 - math.exp(-dt_sec / tau))
        next_c += rng.gauss(0, self.noise_c)
        return next_c
