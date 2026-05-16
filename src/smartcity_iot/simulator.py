from __future__ import annotations

import math
import random
from dataclasses import dataclass
from datetime import datetime, timedelta

from smartcity_iot.models import HouseholdProfile, TelemetrySnapshot


@dataclass(slots=True)
class UnitRuntime:
    energy_today_kwh: float = 0.0
    last_power_w: float = 0.0
    gas_ticks: int = 0
    smoke_ticks: int = 0
    overload_ticks: int = 0
    water_ticks: int = 0
    door_ticks: int = 0
    air_ticks: int = 0
    motion_silence_ticks: int = 0
    day_of_year: int = 0


def build_profiles(*, household_count: int = 24, seed: int | None = None) -> list[HouseholdProfile]:
    rng = random.Random(seed)
    profiles: list[HouseholdProfile] = []
    building_labels = ["A", "B", "C", "D", "E"]
    household_types = ("family", "elderly", "rental")
    for idx in range(max(1, household_count)):
        building = building_labels[idx % len(building_labels)]
        floor = idx % 12 + 1
        unit_id = f"{building}-{floor:02d}{idx % 4 + 1:02d}"
        household_type = household_types[idx % len(household_types)]
        residents = 1 if household_type == "elderly" else (2 if household_type == "rental" else 3 + idx % 2)
        has_elderly = household_type == "elderly" or (household_type == "family" and idx % 5 == 0)
        vulnerability = round(0.35 + (idx % 7) * 0.07 + rng.uniform(-0.04, 0.04), 2)
        base_load_w = 260 + (idx % 6) * 45 + rng.uniform(-35, 35)
        base_temp_c = 24.0 + (idx % 5) * 0.3 + rng.uniform(-0.4, 0.4)
        base_humidity_pct = 52.0 + (idx % 6) * 1.6 + rng.uniform(-2, 2)
        profiles.append(
            HouseholdProfile(
                unit_id=unit_id,
                building_id=building,
                floor=floor,
                household_type=household_type,
                residents=residents,
                has_elderly=has_elderly,
                vulnerability=vulnerability,
                base_load_w=base_load_w,
                base_temp_c=base_temp_c,
                base_humidity_pct=base_humidity_pct,
            )
        )
    return profiles


class CommunitySimulator:
    def __init__(
        self,
        profiles: list[HouseholdProfile],
        *,
        seed: int | None = None,
        step_minutes: int = 5,
        start_time: datetime | None = None,
    ) -> None:
        if not profiles:
            raise ValueError("profiles must not be empty")
        self.profiles = profiles
        self.rand = random.Random(seed)
        self.step_minutes = step_minutes
        self.sim_time = (start_time or datetime.now()).replace(second=0, microsecond=0)
        self.tick_index = 0
        self.runtime = {profile.unit_id: UnitRuntime(day_of_year=self.sim_time.timetuple().tm_yday) for profile in profiles}

    def _meal_factor(self, hour: float) -> float:
        return max(math.exp(-((hour - center) ** 2) / 1.6) for center in (7.5, 12.0, 19.0))

    def _occupancy_probability(self, profile: HouseholdProfile, hour: float) -> float:
        if profile.household_type == "family":
            if 8 <= hour < 17:
                return 0.28
            if 17 <= hour < 23:
                return 0.92
            return 0.74
        if profile.household_type == "elderly":
            if 0 <= hour < 6:
                return 0.86
            if 6 <= hour < 20:
                return 0.96
            return 0.9
        if 9 <= hour < 18:
            return 0.42
        if 18 <= hour < 24:
            return 0.78
        return 0.51

    def _inject_periodic_challenge(self) -> None:
        if self.tick_index % 12 != 0:
            return
        profile = self.rand.choice(self.profiles)
        runtime = self.runtime[profile.unit_id]
        incident = self.rand.choice(("gas", "water", "overload", "smoke"))
        if incident == "gas":
            runtime.gas_ticks = max(runtime.gas_ticks, self.rand.randint(4, 9))
        elif incident == "water":
            runtime.water_ticks = max(runtime.water_ticks, self.rand.randint(5, 12))
        elif incident == "overload":
            runtime.overload_ticks = max(runtime.overload_ticks, self.rand.randint(4, 8))
        elif incident == "smoke":
            runtime.smoke_ticks = max(runtime.smoke_ticks, self.rand.randint(4, 10))

    def _simulate_unit(self, profile: HouseholdProfile, runtime: UnitRuntime, hour: float) -> TelemetrySnapshot:
        meal = self._meal_factor(hour)
        occupancy = self.rand.random() < self._occupancy_probability(profile, hour)

        stove_on = occupancy and self.rand.random() < min(0.95, meal * (0.62 if profile.household_type == "family" else 0.4))
        air_conditioner_on = occupancy and self.rand.random() < 0.52
        water_heater_on = occupancy and self.rand.random() < (0.2 if 6 <= hour <= 9 else 0.08)

        if runtime.gas_ticks == 0 and stove_on and self.rand.random() < 0.018 * profile.vulnerability:
            runtime.gas_ticks = self.rand.randint(4, 10)
        if runtime.smoke_ticks == 0 and stove_on and self.rand.random() < 0.04 * profile.vulnerability:
            runtime.smoke_ticks = self.rand.randint(3, 8)
        if runtime.overload_ticks == 0 and self.rand.random() < 0.012 * profile.vulnerability:
            runtime.overload_ticks = self.rand.randint(4, 9)
        if runtime.water_ticks == 0 and self.rand.random() < 0.006 * profile.vulnerability:
            runtime.water_ticks = self.rand.randint(6, 15)
        if runtime.air_ticks == 0 and self.rand.random() < 0.007 * profile.vulnerability:
            runtime.air_ticks = self.rand.randint(8, 18)
        if runtime.door_ticks == 0 and not occupancy and (hour >= 23 or hour < 5) and self.rand.random() < 0.008:
            runtime.door_ticks = self.rand.randint(2, 6)

        gas_incident = runtime.gas_ticks > 0
        smoke_incident = runtime.smoke_ticks > 0
        overload_incident = runtime.overload_ticks > 0
        water_incident = runtime.water_ticks > 0
        air_incident = runtime.air_ticks > 0
        door_incident = runtime.door_ticks > 0

        outdoor_wave = 1.8 * math.sin((hour - 5) / 24 * math.tau)
        temperature_c = (
            profile.base_temp_c
            + outdoor_wave
            + (1.5 if stove_on else 0.0)
            + (0.7 if occupancy else -0.3)
            - (1.4 if air_conditioner_on else 0.0)
            + self.rand.uniform(-0.4, 0.4)
        )
        humidity_pct = (
            profile.base_humidity_pct
            + 4.5 * math.sin((hour + 1.5) / 24 * math.tau)
            + (6.0 if water_incident else 0.0)
            + self.rand.uniform(-2.2, 2.2)
        )
        gas_ppm = 4.0 + (10.0 if stove_on else 0.0) + (self.rand.uniform(14.0, 36.0) if gas_incident else 0.0) + self.rand.uniform(0.0, 2.4)
        smoke_ppm = 6.0 + (18.0 if stove_on else 0.0) + (self.rand.uniform(24.0, 56.0) if smoke_incident else 0.0) + self.rand.uniform(0.0, 3.6)
        pm25 = (
            22.0
            + (34.0 if stove_on else 0.0)
            + (self.rand.uniform(30.0, 70.0) if smoke_incident else 0.0)
            + (self.rand.uniform(35.0, 85.0) if air_incident else 0.0)
            - (15.0 if occupancy and self.rand.random() < 0.25 else 0.0)
            + self.rand.uniform(-5.0, 5.0)
        )
        power_w = (
            profile.base_load_w
            + (180.0 if occupancy else 40.0)
            + (1500.0 if stove_on else 0.0)
            + (1100.0 if air_conditioner_on else 0.0)
            + (850.0 if water_heater_on else 0.0)
            + (self.rand.uniform(1500.0, 2600.0) if overload_incident else 0.0)
            + self.rand.uniform(-90.0, 90.0)
        )
        door_open = (stove_on and self.rand.random() < 0.45) or door_incident
        water_leak = water_incident

        if occupancy:
            if profile.household_type == "elderly":
                motion_count = self.rand.randint(0, 5)
            elif profile.household_type == "rental":
                motion_count = self.rand.randint(1, 9)
            else:
                motion_count = self.rand.randint(2, 11)
        else:
            motion_count = self.rand.randint(0, 1)

        if profile.has_elderly and occupancy and motion_count <= 1:
            runtime.motion_silence_ticks += 1
        elif occupancy:
            runtime.motion_silence_ticks = max(0, runtime.motion_silence_ticks - 1)
        else:
            runtime.motion_silence_ticks = 0

        if runtime.day_of_year != self.sim_time.timetuple().tm_yday:
            runtime.energy_today_kwh = 0.0
            runtime.day_of_year = self.sim_time.timetuple().tm_yday
        runtime.energy_today_kwh += max(0.05, power_w / 1000 * (self.step_minutes / 60))

        power_delta = power_w - runtime.last_power_w
        runtime.last_power_w = power_w

        tags: list[str] = []
        if stove_on:
            tags.append("cooking")
        if gas_incident:
            tags.append("gas_risk")
        if smoke_incident:
            tags.append("smoke_risk")
        if overload_incident:
            tags.append("power_risk")
        if water_incident:
            tags.append("water_risk")
        if air_incident:
            tags.append("air_risk")
        if not tags:
            tags.append("stable")

        mode = "standby"
        if any((gas_incident, smoke_incident, overload_incident, water_incident, door_incident)):
            mode = "incident"
        elif stove_on:
            mode = "cooking"
        elif occupancy:
            mode = "occupied"

        risk_score = (
            8.0
            + max(0.0, gas_ppm - 16.0) * 1.7
            + max(0.0, smoke_ppm - 28.0) * 0.82
            + max(0.0, pm25 - 90.0) * 0.2
            + max(0.0, power_w - 3000.0) * 0.01
            + (30.0 if water_leak else 0.0)
            + (12.0 if door_incident else 0.0)
            + (12.0 if profile.has_elderly and runtime.motion_silence_ticks >= 6 else 0.0)
        )
        risk_score = max(1.0, min(100.0, risk_score))
        health_score = max(0.0, 100.0 - risk_score * 0.82)

        for attr in ("gas_ticks", "smoke_ticks", "overload_ticks", "water_ticks", "door_ticks", "air_ticks"):
            current = getattr(runtime, attr)
            if current > 0:
                setattr(runtime, attr, current - 1)

        return TelemetrySnapshot(
            unit_id=profile.unit_id,
            building_id=profile.building_id,
            floor=profile.floor,
            household_type=profile.household_type,
            timestamp=self.sim_time.isoformat(timespec="seconds"),
            temperature_c=round(temperature_c, 2),
            humidity_pct=round(max(35.0, min(92.0, humidity_pct)), 2),
            gas_ppm=round(max(0.5, gas_ppm), 2),
            smoke_ppm=round(max(1.0, smoke_ppm), 2),
            pm25=round(max(6.0, pm25), 2),
            power_w=round(max(80.0, power_w), 2),
            power_delta_w=round(power_delta, 2),
            energy_today_kwh=round(runtime.energy_today_kwh, 2),
            water_leak=water_leak,
            door_open=door_open,
            occupancy=occupancy,
            motion_count=motion_count,
            motion_silence_ticks=runtime.motion_silence_ticks,
            risk_score=risk_score,
            health_score=health_score,
            mode=mode,
            tags=tags,
        )

    def step(self) -> tuple[list[TelemetrySnapshot], datetime]:
        self.tick_index += 1
        self.sim_time += timedelta(minutes=self.step_minutes)
        self._inject_periodic_challenge()
        hour = self.sim_time.hour + self.sim_time.minute / 60
        snapshots: list[TelemetrySnapshot] = []
        for profile in self.profiles:
            snapshots.append(self._simulate_unit(profile, self.runtime[profile.unit_id], hour))
        return snapshots, self.sim_time

