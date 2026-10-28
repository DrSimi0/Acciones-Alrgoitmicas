# AGENTS.md — Protocolos Operativos y Memoria del Proyecto

Este archivo define las reglas de interacción, directrices de desarrollo y la memoria persistente para el desarrollo del sistema cuantitativo de Pairs Trading.

## 1. Principios Operativos Fundamentales
1. **Prevención Estricta de Look-Ahead Bias:** Ningún cálculo en tiempo $t$ puede emplear observaciones de $t+1$ en adelante. Todo parámetro (medias, varianzas, hedge ratios, umbrales) debe ser estimado exclusivamente con datos del conjunto de formación o de ventanas móviles pasadas.
2. **Ejecución $t+1$:** Las señales generadas al cierre de la barra $t$ se simulan ejecutándose en la barra $t+1$ para evitar sesgos de cierre simultáneo no reproducible.
3. **Fricciones Realistas:** Ningún backtest es válido sin contemplar costos bidireccionales: comisiones de corretaje, diferencial bid-ask, deslizamiento por impacto de liquidez y costo de préstamo por posiciones cortas (*short-borrow fee*).
4. **No Optimización Prematura:** No sobreajustar parámetros buscando un Sharpe inflado. La prioridad es validar si existe ventaja estadística reproducible fuera de muestra (*out-of-sample*).
5. **Enfoque Modular Incremental:** Cada módulo se implementa con pruebas unitarias que verifiquen rigurosamente su corrección matemática antes de avanzar al siguiente.

## 2. Flujo de Trabajo
- Antes de cada tarea: Revisar `AGENTS.md` y `docs/project_state.md`.
- Tras cada tarea: Actualizar `docs/project_state.md` con el estado alcanzado, registrar decisiones en `docs/decisions.md` y actualizar `docs/research.md`.
- Explicar los conceptos matemáticos en español simple y accesible.
