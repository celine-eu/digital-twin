# EV Charging Readiness – Digital Twin App

## Overview

The **EV Charging Readiness** app is a reference Digital Twin (DT) application designed to demonstrate how meteorological forecasts can be transformed into **actionable, community-level operational indicators**.

Rather than attempting to outperform numerical weather or production models, this app focuses on **semantic lifting**:

> translating forecasted photovoltaic (PV) production and uncertainty into a **decision-oriented indicator** for **electric vehicle (EV) charging coordination** within a Renewable Energy Community (REC).

This README serves as a **baseline specification** for future discussions, refinements, and extensions of the app.

---

## Problem Statement

Energy communities with significant PV capacity and EV adoption face a coordination challenge:

- PV production is **variable and weather-dependent**
- EV charging demand is **flexible but capacity-constrained**
- Poor timing leads to **grid imports, congestion, or curtailment**

Raw weather or solar forecasts alone are insufficient to support operational decisions such as:

- When should EV charging be encouraged or delayed?
- Is the upcoming charging window favorable or risky?
- How confident are we in the forecasted PV availability?

The **EV Charging Readiness** app answers these questions.

---

## What This App Is (and Is Not)

### This app **is**:
- A **decision-support Digital Twin app**
- A **semantic transformer** from forecasts to operational indicators
- Community- and context-aware
- Explainable and policy-ready

### This app **is not**:
- A replacement for meteorological models
- A detailed power system simulator
- A real-time control system

---

## Core Objective

Produce a **time-windowed EV charging readiness indicator** based on:

- Forecasted PV energy availability (DWD ICON-D2)
- Short-term forecast uncertainty (cloudiness variability)
- Community EV charging capacity

The result is a **clear signal** indicating whether EV charging is:

- optimal
- marginal
- suboptimal
- unstable (too uncertain)

---

## Inputs

```json
{
  "community_id": "rec-trento-nord",
  "location": {
    "lat": 46.18,
    "lon": 11.88
  },
  "window_hours": 24,
  "pv_capacity_kw": 1200,
  "ev_charging_capacity_kw": 800
}
```

### Input semantics

| Field | Meaning |
|------|--------|
| `community_id` | Logical identifier of the energy community |
| `location` | Geographic reference point for forecasts |
| `window_hours` | Time horizon for the indicator |
| `pv_capacity_kw` | Installed PV capacity in the community |
| `ev_charging_capacity_kw` | Maximum aggregate EV charging power |

---

## Data Sources

### Primary dataset

- **DWD ICON-D2 solar energy forecasts**
  - Provides forecasted solar energy per square meter
  - Used as the authoritative meteorological baseline

### Enrichment data

- **Cloudiness forecasts**
  - Used to estimate short-term uncertainty and volatility
  - Influences confidence scoring, not energy magnitude

> The app does *not* recompute PV physics; it contextualizes existing forecasts.

---

## Execution Logic (Conceptual)

### 1. Forecast aggregation

Forecasted solar energy values are aggregated over the requested time window.

### 2. Community-scale projection

The app converts per-area solar energy into **expected PV energy** at community scale using:

- installed PV capacity
- simplified efficiency assumptions

### 3. Uncertainty assessment

Cloudiness variability is analyzed to derive a **forecast confidence score**:

- stable conditions → high confidence
- rapidly changing clouds → lower confidence

### 4. Charging envelope comparison

Expected PV energy is compared against the **maximum EV charging energy** possible within the window:

```
ev_charging_capacity_kwh = ev_charging_capacity_kw × window_hours
```

### 5. Indicator classification

The app assigns a readiness class based on surplus, deficit, and uncertainty.

---

## Output

```json
{
  "@type": "EVChargingReadiness",
  "communityId": "rec-trento-nord",
  "windowHours": 24,

  "expectedPVKWh": 5100,
  "evChargingCapacityKWh": 19200,

  "chargingIndicator": "SUBOPTIMAL",
  "confidence": 0.78,

  "drivers": [
    "low PV surplus vs charging capacity",
    "high cloud variability expected"
  ],

  "recommendations": [
    "Encourage delayed charging after 18:00",
    "Prioritize essential fleet vehicles"
  ]
}
```

---

## Indicator States

| State | Meaning |
|------|--------|
| `OPTIMAL` | PV surplus comfortably supports EV charging |
| `MARGINAL` | Partial support, coordination recommended |
| `SUBOPTIMAL` | Likely grid import required |
| `UNSTABLE` | Forecast uncertainty too high |

---

## Why This Is a Digital Twin App

This app demonstrates key DT principles:

- **Context awareness**: community-specific capacities
- **Cross-domain reasoning**: weather → energy → mobility
- **Explainability**: drivers and recommendations are explicit
- **Reusability**: same logic usable via API, batch, or AI agents

---

## Integration Scenarios

This app can serve as:

- Input to EV charging schedulers
- Trigger for demand-response signals
- Constraint provider for battery optimization apps
- Semantic layer for AI-based planners

---

## Extensibility

Planned or possible extensions:

- Historical EV load baselines
- Battery storage interaction
- Grid constraint awareness
- AI-based anomaly detection
- Multi-community aggregation

---

## App Identification

- **Module**: `ev-charging`
- **App key**: `ev-charging-readiness`
- **Version**: `1.0.0`

---

## Status

This README defines the **reference behavior and intent** of the EV Charging Readiness DT app and is intended to evolve as the implementation matures.

