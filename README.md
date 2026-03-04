# Tutorial Interactivo: Filtro de Kalman (Python + Vercel)

Aplicación web para explicar y demostrar el filtro de Kalman lineal en tiempo discreto.

## Funcionalidades

- Definición del modelo discreto `A, B, C, D`.
- Definición de incertidumbre de proceso y medición `Q, R`.
- Ejecución del filtro en dos modos:
  - `simulation`: genera mediciones a partir de un sistema simulado con ruido gaussiano.
  - `offline`: usa mediciones reales cargadas por texto o CSV.
- Discretización exacta desde modelo continuo (`A_c, B_c, Q_c`, `T_s`) usando exponencial de matrices.
- Renderizado de ecuaciones con LaTeX (MathJax).
- Gráficas de:
  - estados estimados (y reales cuando hay simulación),
  - salida medida vs estimada,
  - evolución temporal de covarianza (`tr(P)` y diagonales),
  - innovación.

## Estructura

- `api/index.py`: backend Flask + endpoints.
- `templates/index.html`: interfaz principal.
- `static/styles.css`: estilos responsivos.
- `static/app.js`: lógica cliente y gráficas.
- `vercel.json`: configuración de despliegue en Vercel.

## Ejecutar localmente

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python api/index.py
```

Abrir: <http://localhost:8000>

## Desplegar en Vercel

1. Sube este proyecto a un repositorio Git.
2. En Vercel, crea un proyecto importando el repo.
3. Vercel detectará `vercel.json` y desplegará la función Python.

No se requiere framework adicional.
