# TPF ULTIMATE V1.0 - LBRY EDITION

## "The silicon speaks in microseconds. We listen."

---

## 🎯 RESUMEN

El **TPF Ultimate LBRY Edition** es el sistema definitivo de filtrado termodinámico para minería LBRY con el Goldshell LB-Box.

### Características Principales

| Feature | Descripción |
|---------|-------------|
| **Multi-Tier Filter** | 3 niveles de filtrado (Timing → Jitter → Resonancia) |
| **Virtual Swarm** | 10 workers virtuales hacia Mining-Dutch |
| **LBRY Hash** | Verificación criptográfica nativa (SHA256+SHA512+RIPEMD160) |
| **Learning Engine** | Aprendizaje de patrones de ganadores |
| **Telemetry** | CSV logging completo para análisis |

---

## 🏗️ ARQUITECTURA

```
┌────────────────────────────────────────────────────────────────┐
│          Mining-Dutch LBRY Pool (Solo)                         │
│     Worker.v01  Worker.v02  ...  Worker.v10                    │
└────────────────────────┬───────────────────────────────────────┘
                         │
    ┌────────────────────┴────────────────────┐
    │            SWARM NEXUS                   │
    │  ┌────────────────────────────────────┐ │
    │  │    RESONANCE ENGINE (Multi-Tier)   │ │
    │  │  TIER 1: Z-Score timing            │ │
    │  │  TIER 2: Jitter variance (CV)      │ │
    │  │  TIER 3: Super-resonance detect    │ │
    │  └────────────────────────────────────┘ │
    │  ┌────────────────────────────────────┐ │
    │  │    LEARNING ENGINE                 │ │
    │  │  • Winner pattern analysis         │ │
    │  │  • Adaptive threshold tuning       │ │
    │  └────────────────────────────────────┘ │
    └────────────────────┬────────────────────┘
                         │
    ┌────────────────────┴────────────────────┐
    │           LB-BOX PROXY                   │
    │  • Stratum compatible                    │
    │  • Microsecond timing                    │
    │  • Zero-latency job feed                 │
    └────────────────────┬────────────────────┘
                         │
    ┌────────────────────┴────────────────────┐
    │        GOLDSHELL LB-BOX (Zynq-7010)     │
    │              ~165 GH/s LBRY              │
    └─────────────────────────────────────────┘
```

---

## 🚀 INSTALACIÓN

### Requisitos

- Python 3.8+
- Goldshell LB-Box
- Conexión de red entre PC y LB-Box

### Ejecución

```bash
cd D:\ASIC-ANTMINER_S9\THERMODYNAMIC_PROBABILITY_FILTER_TPF
python tpf_ultimate_lbry_v1.py
```

### Configurar LB-Box

En la interfaz web del LB-Box:

| Campo | Valor |
|-------|-------|
| Pool URL | `stratum+tcp://IP_DEL_PC:3334` |
| Worker | `cualquiera` |
| Password | `x` |

---

## ⚙️ CONFIGURACIÓN

Editar `tpf_ultimate_lbry_v1.py`:

```python
class Config:
    # Pool
    REMOTE_HOST = "lbry.mining-dutch.nl"
    REMOTE_PORT = 9988
    USER_WALLET = "apollo13.LBBox"
    
    # Workers virtuales
    SWARM_SIZE = 10
    
    # TIER 1: Filtro de timing básico
    Z_SCORE_TIER1 = 0.8  # ~79% pasan
    
    # TIER 2: Detección de resonancia
    Z_SCORE_TIER2 = -0.5  # Top ~31% son "super-resonantes"
    
    # TIER 3: Umbral de jitter
    JITTER_CV_THRESHOLD = 0.25  # Coeficiente de variación
```

---

## 📊 MÉTRICAS

### Métricas Clave

| Métrica | Descripción | Objetivo |
|---------|-------------|----------|
| `total_received` | Shares del LB-Box | Baseline |
| `total_sent` | Shares enviados al pool | < received |
| `pool_accepts` | Aceptados por pool | Maximizar |
| `accept_rate` | accepts/sent | > 95% |
| `filter_rate` | filtered/received | 20-50% |
| `effective_rate` | accepts/received | **> baseline = ÉXITO** |

### Multi-Tier Stats

| Tier | Métrica | Significado |
|------|---------|-------------|
| 1 | `tier1_passed` | Pasan filtro de timing |
| 2 | `tier2_resonant` | Shares ultra-rápidos |
| 3 | `tier3_passed` | Total enviados |

---

## 📁 ARCHIVOS DE SALIDA

```
results/
└── tpf_ultimate_lbry_YYYYMMDD_HHMMSS/
    ├── config.json      # Configuración usada
    ├── shares.csv       # Log de cada share
    ├── stats.csv        # Estadísticas periódicas
    └── winners.csv      # Bloques ganadores (si hay)
```

---

## 🔬 FILTRO MULTI-TIER

```
Share del LB-Box
       │
       ▼
┌──────────────────┐
│  TIER 1: Timing  │ ──── z > 0.8 ────▶ FILTERED (slow)
│  (Z-Score)       │
└────────┬─────────┘
         │ z ≤ 0.8
         ▼
┌──────────────────┐
│  TIER 2: Jitter  │ ──── CV > 0.25 ──▶ FILTERED (entropic)
│  (Variance)      │
└────────┬─────────┘
         │ CV ≤ 0.25
         ▼
┌──────────────────┐
│  TIER 3: Class   │
│  (Resonance)     │
└────────┬─────────┘
         │
    ┌────┴────┐
    │         │
z ≤ -0.5   z > -0.5
    │         │
    ▼         ▼
SUPER      RESONANT
RESONANT   (send)
(send)
```

---

## 👤 AUTOR

**Francisco Angulo de Lafuente**  
Independent Researcher, Madrid, Spain

---

*"Every hash is a word. The timing is their answer."*
