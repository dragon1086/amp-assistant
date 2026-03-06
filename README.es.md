# amp — Motor de Debate con IA

> **Dos IAs argumentan. Tú obtienes una mejor respuesta.**

[![PyPI](https://img.shields.io/pypi/v/amp-reasoning)](https://pypi.org/project/amp-reasoning/)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue)](https://python.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

<div align="center">

![banner](docs/assets/banner.png)

</div>


**Leer en otros idiomas:** [English](README.md) · [한국어](README.ko.md) · [日本語](README.ja.md) · [中文](README.zh.md)

---

## ¿Por qué amp?

Una sola IA tiene puntos ciegos — fue entrenada con los mismos datos, tiene los mismos sesgos y tiende a dar la respuesta "segura". **amp ejecuta dos IAs independientes en paralelo, las hace debatir y sintetiza una mejor respuesta a partir de ambas perspectivas.**

```
Tu pregunta
       │
       ├──────────────────────────────────────┐
       ▼                                      ▼
  Agente A (GPT-5)                    Agente B (Claude)
  [análisis independiente]             [análisis independiente]
       │                                      │
       └──────────────┬───────────────────────┘
                      ▼
                 Reconciler (sintetizador)
                      │
                      ▼
         Respuesta final  +  puntuación CSER
```

**CSER** (Cross-agent Semantic Entropy Ratio): mide cuán diferente pensaron las dos IAs sobre tu pregunta. Más alto → perspectivas más independientes → mejor síntesis.

---

## Instalación

```bash
pip install amp-reasoning
amp init        # configuración interactiva (~1 minuto)
```

**Uso gratuito con OAuth** (sin necesidad de claves API — requiere suscripción ChatGPT Plus + Claude Max):
```bash
amp login       # autenticación OAuth vía navegador
```

**Instalador en una línea:**
```bash
curl -fsSL https://raw.githubusercontent.com/dragon1086/amp-assistant/main/install.sh | bash
```

---

## Inicio Rápido

```bash
# Pregunta directamente
amp "¿Debería comprar Bitcoin ahora mismo?"
amp "React vs Vue en 2026 — ¿cuál elegir para un nuevo proyecto?"
amp "¿Cuáles son los verdaderos trade-offs entre Rust y Go?"

# Debate profundo de 4 rondas (más lento pero más profundo)
amp --mode emergent "¿Llegará la AGI antes de 2028?"

# Iniciar servidor MCP (para Claude Desktop, Cursor, OpenClaw, etc.)
amp serve
```

---

## Cómo Funciona

<div align="center">

![architecture](docs/assets/architecture.png)

</div>

### Modo predeterminado — análisis independiente de 2 rondas
El Agente A y B analizan tu pregunta **sin ver la respuesta del otro**.
Garantía de independencia real → CSER alto → mejor síntesis.

### Modo Emergent — debate estructurado de 4 rondas
```
Ronda 1:  Agente A analiza
Ronda 2:  Agente B desafía el razonamiento de A
Ronda 3:  Agente A rebate el desafío de B
Ronda 4:  Agente B entrega contrapunto final
              └──► Reconciler sintetiza
```

### Puerta CSER
Si ambas IAs están demasiado de acuerdo (CSER < 0.30), amp escala automáticamente
al debate de 4 rondas para forzar perspectivas más diversas.

---

## Benchmark

Evaluación A/B ciega: amp ON vs GPT-5.2 solo. Gemini como juez (etiquetas de modelo aleatorizadas). N=30 preguntas, 7 dominios.

| Dominio | amp gana | Solo gana | Tasa de éxito amp |
|---------|:--------:|:---------:|:-----------------:|
| Asignación de recursos | 4 | 1 | **80%** |
| Estrategia | 4 | 2 | **67%** |
| Emoción | 3 | 2 | 60% |
| Carrera | 0 | 3 | 0% |
| Relaciones | 1 | 4 | 20% |
| Ética | 1 | 4 | 20% |
| **Total (N=30)** | **13** | **17** | **43%** |

**Interpretación honesta:** amp no es universalmente mejor. Supera significativamente en problemas complejos con múltiples perspectivas válidas (estrategia, asignación de recursos). Para consejos factuales, un solo modelo experto suele ser suficiente.

---

## Arte Previo y Diferenciación

| Proyecto | Origen | Propósito | pip | Memoria KG | CSER | Aislamiento | MCP |
|---------|--------|-----------|:---:|:---:|:---:|:---:|:---:|
| **amp** | OSS | Asesoría de decisiones | ✅ | ✅ | ✅ | ✅ | ✅ |
| llm_multiagent_debate | ICML 2024 | Precisión Math/MMLU | ❌ | ❌ | ❌ | ❌ | ❌ |
| DebateLLM | InstaDeep 2024 | Q&A médico | ❌ | ❌ | ❌ | ❌ | ❌ |
| AutoGen | Microsoft | Automatización de tareas | ✅ | ❌ | ❌ | ❌ | ❌ |
| CrewAI | Comercial | Flujos empresariales | ✅ | ❌ | ❌ | ❌ | ❌ |

**Diferencia clave:** Los papers académicos MAD buscan mejorar precisión en benchmarks cerrados. amp está diseñado para calidad de razonamiento en decisiones abiertas sin respuesta única correcta.

---

## Arquitectura Interna

Detalles técnicos: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)

### Grafo de Conocimiento

```
Almacenamiento : SQLite (~/.amp/kg.db) — un archivo, sin servidor
Embeddings     : OpenAI text-embedding-3-small (1536 dim)
Búsqueda       : similitud coseno numpy — O(n), hasta ~100K nodos
```

### Algoritmo CSER

```python
cser = (len(unique_a) + len(unique_b)) / len(total_ideas)
# unique_a = ideas que solo presentó A
# unique_b = ideas que solo presentó B
# CSER ≥ 0.30 → síntesis continúa | CSER < 0.30 → escala a 4 rondas
```

### Registro de Dominios Dinámico

Para consultas fuera de los 9 dominios integrados, el LLM crea automáticamente un nuevo dominio y lo guarda en SQLite (pool ilimitado). Usa `amp domains` para ver todos los dominios aprendidos.

---

## Configuración

```bash
amp init   # asistente interactivo
amp setup  # configuración completa (modelos, bot de Telegram, plugins)
```

O edita directamente `~/.amp/config.yaml`:

```yaml
agents:
  agent_a:
    provider: openai
    model: gpt-5.2             # gpt-5.2 | gpt-5.4 | gpt-5.4-mini
    reasoning_effort: high     # none | low | medium | high | xhigh

  agent_b:
    provider: anthropic        # más rápido con ANTHROPIC_API_KEY
    model: claude-sonnet-4-6

amp:
  parallel: true      # ejecutar Agent A+B en paralelo (default: true, ~50% más rápido)
  timeout: 90         # tiempo límite por agente en segundos
  kg_path: ~/.amp/kg.db
```

### Opciones de Proveedor

| Proveedor | Velocidad | Costo | Requisito |
|-----------|-----------|-------|-----------|
| `openai` | ⚡⚡⚡ | De pago | `OPENAI_API_KEY` |
| `openai_oauth` | ⚡⚡⚡ | **Gratis** | ChatGPT Plus/Pro + `amp login` |
| `anthropic` | ⚡⚡⚡ | De pago | `ANTHROPIC_API_KEY` |
| `anthropic_oauth` | ⚡⚡ | **Gratis** | Claude Max/Pro + `amp login` |
| `gemini` | ⚡⚡⚡ | De pago | `GEMINI_API_KEY` |
| `deepseek` | ⚡⚡⚡ | Económico | `DEEPSEEK_API_KEY` |
| `mistral` | ⚡⚡⚡ | Económico | `MISTRAL_API_KEY` |
| `local` | ⚡⚡ | Gratis | Ollama en ejecución |

**Combinación completamente gratuita (con ChatGPT Plus + Claude Max):**
```bash
amp login
# → Configura automáticamente openai_oauth × anthropic_oauth
# → Costo de API $0
```

---

## Integraciones

amp incluye múltiples interfaces de serie — conéctalo directamente a tu flujo de trabajo existente.

### Bot de Telegram

Envía preguntas, cambia modos, gestiona plugins y genera imágenes — todo desde Telegram.

```bash
amp bot   # iniciar el bot (requiere TELEGRAM_BOT_TOKEN)
```

| Comando | Descripción |
|---------|-------------|
| `<mensaje>` | Analizar con amp (modo actual) |
| `/mode auto\|solo\|pipeline\|emergent` | Cambiar modo de razonamiento |
| `/imagine <prompt>` | Generar imagen |
| `/plugins` | Lista de plugins + estado |
| `/stats` | Nodos KG + estadísticas de sesión |
| 📷 Foto | Análisis de imagen (plugin image_vision) |

---

### Sistema de Plugins

| Plugin | Función | Por defecto |
|--------|---------|:-----------:|
| `image_vision` | Análisis de fotos (GPT-4o Vision) | ✅ |
| `image_gen` | Generación de imágenes (`/imagine`, Gemini/DALL-E) | ✅ |
| `claude_executor` | Ejecuta Claude Code localmente y devuelve resultados | ❌ |
| `mcp_bridge` | Conecta servidores MCP externos como herramientas de los agentes | ❌ |

```bash
amp plugins
amp plugin enable claude_executor
```

**Plugins externos** — coloca `SKILL.md` + `plugin.py` opcional en `~/.amp/plugins/`.
Compatible con el formato OpenClaw AgentSkills.

---

### Puente MCP (amp → servidores MCP externos)

Durante el razonamiento, los agentes de amp pueden llamar a **servidores MCP externos** como herramientas — acceso en tiempo real a sistemas de archivos, GitHub, búsqueda web, etc.

```yaml
mcp:
  servers:
    - name: filesystem
      url: http://localhost:3001
      enabled: true
    - name: brave-search
      url: http://localhost:3002
      enabled: true
```

---

## Servidor MCP

Compatible con Claude Desktop, Cursor, OpenClaw y cualquier cliente MCP:

```bash
amp serve   # inicia en http://127.0.0.1:3010
```

Añade a tu configuración MCP:
```json
{
  "amp": {
    "url": "http://127.0.0.1:3010"
  }
}
```

| Herramienta | Descripción | Latencia típica |
|-------------|-------------|-----------------|
| `analyze` | análisis independiente de 2 rondas | 15–30s |
| `debate` | debate estructurado de 4 rondas | 30–60s |
| `quick_answer` | respuesta rápida con un solo LLM | ~3s |

---

## Docker

```bash
docker run \
  -e OPENAI_API_KEY=sk-... \
  -e ANTHROPIC_API_KEY=sk-ant-... \
  -p 3010:3010 \
  ghcr.io/dragon1086/amp-assistant

# Con docker-compose
OPENAI_API_KEY=sk-... ANTHROPIC_API_KEY=sk-ant-... docker-compose up
```

---

## API de Python

```python
from amp.core import emergent
from amp.config import load_config

config = load_config()
result = emergent.run(
    query="¿Debería usar Rust o Go para mi backend?",
    context=[],
    config=config,
)

print(result["answer"])
print(f"CSER:       {result['cser']:.2f}")       # cuán diferentes pensaron las IAs
print(f"Acuerdos:   {result['agreements']}")
print(f"Conflictos: {result['conflicts']}")
```

---

## Rendimiento (2026-03, Apple M-series, modo paralelo)

| Configuración | Latencia promedio | Costo/consulta |
|---------------|------------------|----------------|
| GPT-5.2 + Claude Sonnet (API, paralelo) | ~18s | $0.03–0.08 |
| GPT-5.2 + Claude OAuth (paralelo) | ~35s | ~$0.01 |
| GPT-5.2 + GPT-5.2 (mismo proveedor) | ~15s | $0.02–0.05 |

La ejecución paralela A+B ofrece una **mejora de velocidad de ~50%** frente a la secuencial (v0.1.0+).

---

## ¿Por qué Cross-Vendor?

GPT y Claude fueron entrenados por diferentes empresas, con datos distintos y diferentes enfoques de alineación. Tienen más probabilidades de estar genuinamente en desacuerdo sobre la misma pregunta. Esa es la intuición central de amp — **la síntesis cross-vendor produce mejores respuestas que el auto-debate de un solo proveedor.**

---

## Contribuir

```bash
git clone https://github.com/dragon1086/amp-assistant
cd amp-assistant
pip install -e ".[dev]"
pytest tests/ -q
```

Para cambios grandes, abre un Issue primero. Los PRs son bienvenidos.

---

## Licencia

MIT © 2026 amp contributors
