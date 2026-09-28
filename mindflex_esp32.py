import socket
import csv
import time
import os
import argparse
from datetime import datetime

try:
    from colorama import Fore, Style, init as colorama_init
    colorama_init(autoreset=True)
    COLOR = True
except ImportError:
    COLOR = False
    class Fore:
        GREEN = CYAN = YELLOW = RED = MAGENTA = WHITE = ""
    class Style:
        BRIGHT = RESET_ALL = ""

DEFAULT_IP       = "192.168.4.1"
DEFAULT_PORT     = 1234
DEFAULT_DURATION = 600
BUFFER_SIZE      = 4096
OUTPUT_DIR       = "Erick"  # Cambiar para nueva carpeta (Hombres, Mujeres)

# Se elimina "raw" porque este MindFlex no envía la señal RAW EEG
EXPECTED_COLUMNS = [
    "timestamp_ms", "signal_quality", "attention", "meditation",
    "blink",
    "delta", "theta", "alpha_low", "alpha_high",
    "beta_low", "beta_high", "gamma_low", "gamma_mid"
]

def cprint(msg, color="", bright=False):
    prefix = (Style.BRIGHT if bright else "") + color
    print(f"{prefix}{msg}{Style.RESET_ALL}")

def print_header():
    cprint("=" * 60, Fore.CYAN, bright=True)
    cprint("MINDFLEX EEG — Grabador de sesión", Fore.CYAN, bright=True)
    cprint("=" * 60, Fore.CYAN, bright=True)

def print_row(row, elapsed, total, count):
    sig = int(row.get("signal_quality", 200))
    att = int(row.get("attention", 0))
    med = int(row.get("meditation", 0))

    sig_color = Fore.GREEN if sig == 0 else (Fore.YELLOW if sig < 100 else Fore.RED)
    att_color = Fore.GREEN if att >= 50 else Fore.WHITE
    med_color = Fore.GREEN if med >= 50 else Fore.WHITE

    bar_len  = 20
    progress = int((elapsed / total) * bar_len)
    bar      = "█" * progress + "░" * (bar_len - progress)
    pct      = (elapsed / total) * 100

    print(
        f"\r{Fore.CYAN}[{bar}]{Style.RESET_ALL} "
        f"{pct:5.1f}% | #{count:4d} | "
        f"SQ:{sig_color}{sig:3d}{Style.RESET_ALL} | "
        f"ATT:{att_color}{att:3d}{Style.RESET_ALL} | "
        f"MED:{med_color}{med:3d}{Style.RESET_ALL}",
        end="", flush=True
    )

class MindflexReceiver:
    def __init__(self, ip, port, duration, output_dir):
        self.ip         = ip
        self.port       = port
        self.duration   = duration
        self.output_dir = output_dir
        self.sock       = None
        self.csv_path   = None
        self.row_count  = 0
        self.header_ok  = False

    def _make_filepath(self):
        os.makedirs(self.output_dir, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return os.path.join(self.output_dir, f"eeg_{stamp}.csv")

    def connect(self):
        cprint(f"\n Conectando a {self.ip}:{self.port} ...", Fore.YELLOW)
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.settimeout(10)
            self.sock.connect((self.ip, self.port))
            self.sock.settimeout(2)
            cprint("Conexión establecida", Fore.GREEN, bright=True)
            return True
        except ConnectionRefusedError:
            cprint("Conexión rechazada. ¿Está el ESP32 encendido?", Fore.RED)
        except socket.timeout:
            cprint("Tiempo de espera agotado. Verifica IP y red.", Fore.RED)
        except OSError as e:
            cprint(f"Error de red: {e}", Fore.RED)
        return False

    def record(self):
        self.csv_path = self._make_filepath()
        cprint(f"\n Guardando en: {self.csv_path}", Fore.CYAN)
        cprint(f"Duración: {self.duration} segundos\n", Fore.CYAN)

        leftover   = ""
        start_time = time.time()
        columns    = None

        with open(self.csv_path, "w", newline="", encoding="utf-8") as f:
            writer = None
            try:
                while True:
                    elapsed = time.time() - start_time
                    if elapsed >= self.duration:
                        break

                    try:
                        chunk = self.sock.recv(BUFFER_SIZE).decode("utf-8", errors="replace")
                    except socket.timeout:
                        continue
                    except ConnectionResetError:
                        cprint("\n Conexión cerrada por el ESP32.", Fore.YELLOW)
                        break

                    if not chunk:
                        time.sleep(0.01)
                        continue

                    lines    = (leftover + chunk).split("\n")
                    leftover = lines.pop()

                    for line in lines:
                        line = line.strip()
                        if not line:
                            continue

                        if not self.header_ok:
                            columns = [c.strip() for c in line.split(",")]
                            missing = [c for c in EXPECTED_COLUMNS if c not in columns]
                            if missing:
                                cprint(f"\nColumnas no encontradas: {missing}", Fore.YELLOW)
                            writer = csv.DictWriter(f, fieldnames=columns)
                            writer.writeheader()
                            self.header_ok = True
                            continue

                        if writer is None:
                            continue

                        values = line.split(",")
                        if len(values) != len(columns):
                            continue

                        row = dict(zip(columns, values))
                        writer.writerow(row)
                        self.row_count += 1
                        print_row(row, elapsed, self.duration, self.row_count)

            except KeyboardInterrupt:
                cprint("\n\n Grabación interrumpida por el usuario.", Fore.YELLOW)

    def close(self):
        if self.sock:
            try:
                self.sock.close()
            except Exception:
                pass

    def summary(self):
        print()
        cprint("\n" + "=" * 60, Fore.CYAN, bright=True)
        cprint("RESUMEN DE SESIÓN", Fore.CYAN, bright=True)
        cprint("=" * 60, Fore.CYAN, bright=True)
        cprint(f"  Filas grabadas : {self.row_count}", Fore.WHITE, bright=True)
        if self.row_count > 0 and self.duration > 0:
            hz = self.row_count / self.duration
            cprint(f"  Frecuencia     : {hz:.1f} Hz", Fore.WHITE, bright=True)
        if self.csv_path:
            size_kb = os.path.getsize(self.csv_path) / 1024 if os.path.exists(self.csv_path) else 0
            cprint(f"  Archivo        : {self.csv_path}", Fore.GREEN, bright=True)
            cprint(f"  Tamaño         : {size_kb:.1f} KB", Fore.WHITE)
        cprint("=" * 60, Fore.CYAN, bright=True)

def parse_args():
    parser = argparse.ArgumentParser(
        description="Receptor de datos EEG Mindflex desde ESP32 → CSV"
    )
    parser.add_argument("--ip",       default=DEFAULT_IP)
    parser.add_argument("--port",     type=int, default=DEFAULT_PORT)
    parser.add_argument("--duration", type=int, default=DEFAULT_DURATION)
    parser.add_argument("--output",   default=OUTPUT_DIR)
    return parser.parse_args()

def main():
    args = parse_args()
    print_header()
    cprint(f"\n  IP      : {args.ip}", Fore.WHITE)
    cprint(f"  Puerto  : {args.port}", Fore.WHITE)
    cprint(f"  Duración: {args.duration} s", Fore.WHITE)
    cprint(f"  Salida  : {args.output}/", Fore.WHITE)

    receiver = MindflexReceiver(
        ip=args.ip, port=args.port,
        duration=args.duration, output_dir=args.output
    )

    if not receiver.connect():
        cprint("\nVerifica que:\n"
               "   1. Tu laptop esté conectada a la red 'ESP32_EEG'\n"
               "   2. El ESP32 esté encendido y ejecutando el sketch\n"
               "   3. La IP sea 192.168.4.1", Fore.YELLOW)
        return

    receiver.record()
    receiver.close()
    receiver.summary()

if __name__ == "__main__":
    main()








