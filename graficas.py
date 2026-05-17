import argparse
import os
import glob
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from matplotlib.ticker import MaxNLocator
import matplotlib.patches as mpatches

#  TEMA VISUAL
BG      = "#111318"
PANEL   = "#1a1d24"
GRID    = "#2a2d36"
BORDER  = "#3a3d48"
TEXT    = "#f0f2f8"
SUBTEXT = "#8890a8"

C = {
    "attention":      "#00CFFF",
    "meditation":     "#00FF9C",
    "signal_quality": "#FF4560",
    "blink":          "#FFD200",
    "raw":            "#FF8C00",
    "delta":          "#6BFFF2",
    "theta":          "#B8FF3C",
    "alpha_low":      "#FF6BFF",
    "alpha_high":     "#FF3CAA",
    "beta_low":       "#4DC3FF",
    "beta_high":      "#A78BFF",
    "gamma_low":      "#FFE066",
    "gamma_mid":      "#FF7070",
}

#  CARGA DE CSV
def load_csv(filepath: str) -> pd.DataFrame:
    df = pd.read_csv(filepath)
    df.columns = df.columns.str.strip()
    if "timestamp_ms" in df.columns:
        df["time_s"] = df["timestamp_ms"] / 1000.0
    else:
        df["time_s"] = df.index.astype(float)
    for col in df.columns:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df.dropna(subset=["time_s"], inplace=True)
    return df

def find_latest_csv(folder="eeg_sessions"):
    files = glob.glob(os.path.join(folder, "eeg_*.csv"))
    return max(files, key=os.path.getmtime) if files else None

#  HELPERS DE ESTILO
def style_ax(ax, title="", xlabel=False):
    ax.set_facecolor(PANEL)
    for spine in ax.spines.values():
        spine.set_edgecolor(BORDER)
        spine.set_linewidth(0.8)
    ax.tick_params(colors=SUBTEXT, labelsize=7, length=3)
    ax.grid(True, color=GRID, linewidth=0.5, linestyle="--", alpha=0.8)
    ax.yaxis.set_major_locator(MaxNLocator(nbins=3, integer=True))
    if title:
        ax.set_title(title, color=TEXT, fontsize=8,
                     fontweight="bold", loc="left", pad=4)
    if xlabel:
        ax.set_xlabel("Tiempo (s)", color=SUBTEXT, fontsize=7, labelpad=3)
    ax.set_ylabel("")

def plot_line(ax, x, y, color, lw=1.3, fill_alpha=0.10):
    ax.plot(x, y, color=color, linewidth=lw, solid_capstyle="round")
    ax.fill_between(x, y, alpha=fill_alpha, color=color)
    ax.set_xlim(x.iloc[0], x.iloc[-1])

def auto_ylim(series, padding=0.15):
    """Escala el eje Y al rango real de los datos + padding."""
    vmin, vmax = series.min(), series.max()
    margin = max((vmax - vmin) * padding, abs(vmax) * 0.05, 1e-6)
    return vmin - margin, vmax + margin

def make_legend(ax, entries):
    patches = [mpatches.Patch(color=c, label=l) for l, c in entries]
    ax.legend(
        handles=patches, loc="upper right", fontsize=7,
        facecolor=BG, edgecolor=BORDER, labelcolor=TEXT,
        framealpha=0.9, handlelength=1.0, handleheight=0.7,
        borderpad=0.4, labelspacing=0.25
    )

#  FIGURA PRINCIPAL
def plot_session(df: pd.DataFrame, filename: str):
    t        = df["time_s"]
    duration = t.iloc[-1] - t.iloc[0]
    n        = len(df)

    fig = plt.figure(figsize=(18, 13), facecolor=BG)

    # Cabecera: título + stats en dos líneas bien separadas
    fig.text(0.012, 0.988,
             f"Sesión EEG — {filename}",
             color=TEXT, fontsize=12, fontweight="bold",
             va="top", ha="left")
    fig.text(0.012, 0.970,
             f"Duración: {duration:.1f} s   |   Muestras: {n}   |   ~{n/max(duration,1):.1f} Hz",
             color=SUBTEXT, fontsize=8, va="top", ha="left")

    #GridSpec
    # Fila 0 (grande):  Atención & Meditación   — full width
    # Fila 1 (media):   RAW                     — full width
    # Fila 2 (pequeña): Calidad señal | Parpadeo
    # Fila 3 (pequeña): Delta/Theta  | Alpha
    # Fila 4 (pequeña): Beta         | Gamma
    # Por esto:
    gs = gridspec.GridSpec(
    4, 2,
    figure=fig,
    height_ratios=[2.2, 1.0, 1.0, 1.0],
    hspace=0.58,
    wspace=0.28,
    left=0.055, right=0.98,
    top=0.945, bottom=0.042
    )

    #1. ATENCIÓN & MEDITACIÓN
    ax0 = fig.add_subplot(gs[0, :])
    style_ax(ax0, "Atención & Meditación")
    if "attention" in df.columns:
        plot_line(ax0, t, df["attention"],  C["attention"],  lw=1.8)
    if "meditation" in df.columns:
        plot_line(ax0, t, df["meditation"], C["meditation"], lw=1.8)
    ax0.axhline(50, color=BORDER, linewidth=0.7, linestyle=":", alpha=0.7)
    ax0.set_ylim(-3, 108)
    ax0.set_ylabel("Nivel (0–100)", color=SUBTEXT, fontsize=7)
    make_legend(ax0, [("Atención", C["attention"]),
                      ("Meditación", C["meditation"])])

    #3. CALIDAD DE SEÑAL
    ax_sq = fig.add_subplot(gs[1, 0])
    style_ax(ax_sq, "Calidad de señal  (0 = perfecta)")
    if "signal_quality" in df.columns:
        plot_line(ax_sq, t, df["signal_quality"],
                  C["signal_quality"], fill_alpha=0.12)
    ax_sq.invert_yaxis()
    ax_sq.set_ylabel("SQ", color=SUBTEXT, fontsize=7)

    #4. PARPADEO
    ax_bl = fig.add_subplot(gs[1, 1])
    style_ax(ax_bl, "Parpadeo")
    if "blink" in df.columns:
        blink = df["blink"]
        ax_bl.vlines(t, 0, blink, color=C["blink"], linewidth=1.0, alpha=0.9)
        ax_bl.set_xlim(t.iloc[0], t.iloc[-1])
        # Limitar eje al percentil 99 para que los picos sean visibles
        p99 = blink[blink > 0].quantile(0.99) if (blink > 0).any() else 1
        ax_bl.set_ylim(0, p99 * 1.25)
    ax_bl.set_ylabel("Intensidad", color=SUBTEXT, fontsize=7)

    #5. DELTA / THETA
    ax_dt = fig.add_subplot(gs[2, 0])
    style_ax(ax_dt, "Delta / Theta")
    for col in ("delta", "theta"):
        if col in df.columns:
            plot_line(ax_dt, t, df[col], C[col], fill_alpha=0.07)
    ax_dt.set_ylabel("Potencia", color=SUBTEXT, fontsize=7)
    make_legend(ax_dt, [("Delta", C["delta"]), ("Theta", C["theta"])])

    #6. ALPHA
    ax_al = fig.add_subplot(gs[2, 1])
    style_ax(ax_al, "Alpha")
    for col, lbl in [("alpha_low","Alpha Low"),("alpha_high","Alpha High")]:
        if col in df.columns:
            plot_line(ax_al, t, df[col], C[col], fill_alpha=0.07)
    ax_al.set_ylabel("Potencia", color=SUBTEXT, fontsize=7)
    make_legend(ax_al, [("Alpha Low", C["alpha_low"]),
                        ("Alpha High", C["alpha_high"])])

    #7. BETA
    ax_be = fig.add_subplot(gs[3, 0])
    style_ax(ax_be, "Beta", xlabel=True)
    for col, lbl in [("beta_low","Beta Low"),("beta_high","Beta High")]:
        if col in df.columns:
            plot_line(ax_be, t, df[col], C[col], fill_alpha=0.07)
    ax_be.set_ylabel("Potencia", color=SUBTEXT, fontsize=7)
    make_legend(ax_be, [("Beta Low", C["beta_low"]),
                        ("Beta High", C["beta_high"])])

    #8. GAMMA
    ax_ga = fig.add_subplot(gs[3, 1])
    style_ax(ax_ga, "Gamma", xlabel=True)
    for col, lbl in [("gamma_low","Gamma Low"),("gamma_mid","Gamma Mid")]:
        if col in df.columns:
            plot_line(ax_ga, t, df[col], C[col], fill_alpha=0.07)
    ax_ga.set_ylabel("Potencia", color=SUBTEXT, fontsize=7)
    make_legend(ax_ga, [("Gamma Low", C["gamma_low"]),
                        ("Gamma Mid", C["gamma_mid"])])
    plt.show()

#  MAIN
def parse_args():
    p = argparse.ArgumentParser(
        description="Visualizador EEG Mindflex v3",
        formatter_class=argparse.RawTextHelpFormatter
    )
    p.add_argument(
        "--file", default=None,
        metavar="RUTA",
        help="Ruta al CSV.\n"
             "Ejemplos:\n"
             "  --file eeg_sessions/eeg_20260421_104624.csv\n"
             "  --file C:/datos/mi_sesion.csv\n"
             "(default: archivo más reciente en eeg_sessions/)"
    )
    return p.parse_args()

def main():
    args = parse_args()

    filepath = args.file
    if filepath is None:
        filepath = find_latest_csv()
        if filepath is None:
            print("No se encontró ningún CSV en eeg_sessions/")
            print("Usa: python mindflex_plot.py --file ruta/archivo.csv")
            return

    if not os.path.exists(filepath):
        print(f"Archivo no encontrado: {filepath}")
        return

    df = load_csv(filepath)
    plot_session(df, os.path.basename(filepath))

if __name__ == "__main__":
    main()
