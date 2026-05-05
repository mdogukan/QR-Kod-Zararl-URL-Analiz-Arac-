# Privacy Shield

Real-time webcam-based privacy protection. Dims the left and right sides of your
screen whenever more than one face is detected, keeping only the center visible.

## Requirements

- Python 3.10+
- A webcam

## Setup

```bash
cd privacy-shield
pip install -r requirements.txt
```

## Run

```bash
python main.py
```

Press **Ctrl+C** in the terminal to quit.

## Configuration

| File | Constant | Description |
|------|----------|-------------|
| `overlay.py` | `CENTER_VISIBLE_RATIO` | Fraction of screen kept clear (default `0.5` = 50 %) |
| `overlay.py` | `MAX_ALPHA` | Darkness of side panels 0–255 (default `180`) |
| `overlay.py` | `FADE_STEP` | Fade speed per 30 ms tick (default `12`) |
| `main.py` | `DEBOUNCE_FRAMES` | Readings before toggling state (default `3`) |

## Notes

- The overlay is **click-through** — your mouse and keyboard work normally.
- The camera feed is processed in the background and never displayed.
- Tested on Windows 10/11. On Linux you may need `python3-pyqt5` from your package manager.
