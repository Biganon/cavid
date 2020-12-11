import sys
import os
import subprocess
import re
import pyperclip
import time
from termcolor import colored
from datetime import datetime
from multiprocessing import Pool, Value, Lock
from ctypes import c_int

original = sys.argv[1]
threshold = 0.2
mask = "mask.png"

LOG_INFO = 0
LOG_WARNING = 1
LOG_ERROR = 2
LOG_SUCCESS = 3
LOG_INPUT = 4

def log(string, level, *args, **kwargs):
    now = datetime.now().strftime("%H:%M:%S")
    color = ("white", "yellow", "red", "green", "blue")[level]
    code = ("I", "W", "E", "S", "?")[level]
    print(colored(f"[{now}] [{code}] {string}", color), *args, **kwargs)

def check_or_die(cp):
    if cp.returncode != 0:
        log(f"La dernière commande s'est terminée avec un code de retour non nul. Arrêt. {cp.stderr}", LOG_ERROR)
        sys.exit()

### DECOUPAGE

log(f"Commence l'extraction des timecodes de changements de scène (seuil = {threshold})...", LOG_INFO)
cp = subprocess.run(["ffmpeg", "-i", original, "-filter:v", "select='gt(scene,0.2)',showinfo", "-f", "null", "-"],
                    capture_output=True, stdin=subprocess.DEVNULL)

check_or_die(cp)

timecodes = re.findall(r"pts_time:([0-9.]+)", cp.stderr.decode("utf-8"))

cp = subprocess.run(["ffprobe", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", original],
                    capture_output=True, stdin=subprocess.DEVNULL)
check_or_die(cp)

start = "0.0"
end = cp.stdout.decode("utf-8").strip()
timecodes.insert(0, start)
timecodes.append(end)

log(f"Extraction terminée.", LOG_SUCCESS)
log(f"Commence la création des extraits...", LOG_INFO)

counter = Value(c_int)
counter_lock = Lock()
def create_extract(original, start, end, index):
    filename = str(index).zfill(3) + ".mp4"
    cp = subprocess.run(["ffmpeg", "-i", original, "-ss", start, "-to", end, "-c", "copy", filename],
                        capture_output=True, stdin=subprocess.DEVNULL)
    check_or_die(cp)
    with counter_lock:
        counter.value += 1
        log(f"Extrait créé ({counter.value}/{len(timecodes)-1})", LOG_SUCCESS)    

parameters = []
for i in range(len(timecodes)-1):
    start = timecodes[i]
    end = timecodes[i+1]
    index = i+1
    parameters.append((original, start, end, index))
with Pool() as pool:
    pool.starmap(create_extract, parameters)

### TRI

log(f"Ouvrir un navigateur de fichiers (Nautilus ou Thunar conseillés), sélectionner tous les extraits à laisser intouchés, puis copier dans le presse-papiers (ctrl+c).", LOG_INFO)

while True:
    log("Est-ce que c'est fait ? [o = oui, q = quitter] ", LOG_INPUT, end="")
    choice = input().lower()
    if choice == "q":
        sys.exit()
    elif choice == "o":
        clipboard = pyperclip.paste()
        untouched = re.findall(r"[0-9]+\.mp4", clipboard)
        if len(untouched) == 0:
            log("Aucun fichier valide trouvé dans le presse-papiers !", LOG_WARNING)
            continue
        else:
            log(f"{len(untouched)} fichiers vidéo valides trouvés dans le presse-papiers.", LOG_SUCCESS)
            break
    else:
        continue

### CAVIARDAGE

extracts = sorted([f for f in os.listdir() if re.match(r"[0-9]+\.mp4", f) and f not in untouched])
log(f"Commence le caviardage de {len(extracts)} extraits...", LOG_INFO)

counter = Value(c_int)
counter_lock = Lock()
def redact_extract(extract):
    cp = subprocess.run(["ffprobe", "-show_streams", extract], capture_output=True, stdin=subprocess.DEVNULL)
    check_or_die(cp)

    has_video = bool(re.search(r"codec_type=video", cp.stdout.decode("utf-8")))

    if has_video:
        cp = subprocess.run(["ffmpeg", "-i", extract, "-i", mask, "-filter_complex", "[1][0]scale2ref[i][v];[v][i]overlay", "-c:a", "copy", "-max_muxing_queue_size", "1024", f"h{extract}"],
                            capture_output=True, stdin=subprocess.DEVNULL)
    else:
        cp = subprocess.run(["ffmpeg", "-i", extract, "-i", mask, "-acodec", "copy", "-vcodec", "h264", "-max_muxing_queue_size", "1024", f"h{extract}"],
                            capture_output=True, stdin=subprocess.DEVNULL)
    check_or_die(cp)
    with counter_lock:
        counter.value += 1
        log(f"Extrait caviardé ({counter.value}/{len(extracts)})", LOG_SUCCESS)

with Pool() as pool:
    pool.map(redact_extract, extracts)

log("Renomme les extraits caviardés...", LOG_INFO)
for extract in extracts:
    os.rename(f"h{extract}", extract)
log("Extraits renommés.", LOG_SUCCESS)

### NORMALISATION

extracts = sorted([f for f in os.listdir() if re.match(r"[0-9]+\.mp4", f)])
log(f"Commence la normalisation de {len(extracts)} extraits...", LOG_INFO)
counter = Value(c_int)
counter_lock = Lock()
def normalize_extract(extract):
    cp = subprocess.run(["ffmpeg", "-i", extract, "-q", "0", "-max_muxing_queue_size", "1024", f"s{extract}"],
                        capture_output=True, stdin=subprocess.DEVNULL)
    check_or_die(cp)

    with counter_lock:
        counter.value += 1
        log(f"Extrait normalisé ({counter.value}/{len(extracts)})", LOG_SUCCESS)

with Pool() as pool:
    pool.map(normalize_extract, extracts)

log("Renomme les extraits normalisés...", LOG_INFO)
for extract in extracts:
    os.rename(f"s{extract}", extract)
log("Extraits renommés.", LOG_SUCCESS)

### CONCATÉNATION

log("Commence la concaténation finale...", LOG_INFO)
concat_file = ""
for extract in sorted(extracts):
    concat_file += f"file '{extract}'\n"

with open("concat_file.txt", "w") as f:
    f.write(concat_file)

cp = subprocess.run(["ffmpeg", "-f", "concat", "-i", "concat_file.txt", "-c", "copy", "final.mp4"], capture_output=True, stdin=subprocess.DEVNULL)
check_or_die(cp)
log("Concaténation terminée.", LOG_SUCCESS)

### NETTOYAGE

log("Supprime les extraits et le fichier de concaténation...", LOG_INFO)
for extract in extracts:
    os.remove(extract)
os.remove("concat_file.txt")
log("Extraits et fichier de concaténation supprimés.", LOG_SUCCESS)

log("Terminé.", LOG_SUCCESS)
