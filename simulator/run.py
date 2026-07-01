"""Point d'entrée : `python -m simulator.run` envoie la télémétrie vers Redpanda."""
from __future__ import annotations

import json

import click
from confluent_kafka import Producer
from loguru import logger

from ingestion.config import settings
from simulator.fleet import scripted_demo_incident, stream_events


def _producer() -> Producer:
    cfg = settings()
    return Producer({
        "bootstrap.servers": cfg.redpanda_brokers,
        "client.id": "vigistock-simulator",
        "linger.ms": 20,
        "enable.idempotence": True,
    })


def _delivery_cb(err, msg) -> None:
    if err is not None:
        logger.error(f"delivery failed: {err}")


@click.command()
@click.option("--hours", type=float, default=None,
              help="S'arrête après N heures simulées. Par défaut : tourne indéfiniment.")
@click.option("--realtime/--as-fast-as-possible", default=True,
              help="Dort entre les ticks (démo temps réel) ou enchaîne les ticks (CI).")
@click.option("--incident/--no-incident", default=True,
              help="Injecte l'incident cold-chain scripté à t+60s.")
@click.option("--seed", type=int, default=42)
def main(hours: float | None, realtime: bool, incident: bool, seed: int) -> None:
    cfg = settings()
    producer = _producer()
    topic = cfg.redpanda_topic_telemetry

    script = scripted_demo_incident() if incident else None
    logger.info(f"Simulator: topic={topic}, sites={cfg.simulator_sites}, "
                f"fridges/site={cfg.simulator_fridges_per_site}, incident={bool(script)}")

    total = 0
    for batch in stream_events(
        n_sites=cfg.simulator_sites,
        fridges_per_site=cfg.simulator_fridges_per_site,
        tick_seconds=cfg.simulator_tick_seconds,
        hours=hours,
        seed=seed,
        realtime=realtime,
        scripted_incident=script,
    ):
        for event in batch:
            producer.produce(
                topic=topic,
                key=event["fridge_id"].encode(),
                value=json.dumps(event).encode(),
                on_delivery=_delivery_cb,
            )
        producer.poll(0)
        total += len(batch)
        if total % 500 == 0:
            logger.info(f"produced {total} events")

    producer.flush(timeout=30)
    logger.success(f"Simulator done: produced {total} events.")


if __name__ == "__main__":
    main()
