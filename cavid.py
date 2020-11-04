import sys
import os
import subprocess
import re
import pyperclip
from termcolor import colored

original = sys.argv[1]
threshold = 0.3
mask = "mask.png"

LOG_INFO = 0
LOG_WARNING = 1
LOG_ERROR = 2
LOG_SUCCESS = 3
LOG_INPUT = 4

def log(string, level, *args, **kwargs):
    color = ("white", "yellow", "red", "green", "blue")[level]
    code = ("I", "W", "E", "S", "?")[level]
    print(colored(f"[{code}] {string}", color), *args, **kwargs)

def check_or_die(cp):
    if cp.returncode != 0:
        log("La dernière commande s'est terminée avec un code de retour non nul. Arrêt.", LOG_ERROR)
        sys.exit()

log(f"Commence l'extraction des timecodes de changements de scène (seuil = {threshold})...", LOG_INFO)
cp = subprocess.run(["ffmpeg", "-i", original, "-filter:v", "select='gt(scene,0.3)',showinfo", "-f", "null", "-"],
                    capture_output=True)

check_or_die(cp)

timecodes = re.findall(r"pts_time:([0-9.]+)", cp.stderr.decode("utf-8"))

log(f"Extraction terminée, {len(timecodes)} timecodes trouvés.", LOG_SUCCESS)
log(f"Commence la création des extraits...", LOG_INFO)

for i in range(len(timecodes)-1):
    start = timecodes[i]
    end = timecodes[i+1]
    filename = str(i+1).zfill(3) + ".mp4"
    cp = subprocess.run(["ffmpeg", "-i", original, "-ss", start, "-to", end, "-c", "copy", filename],
                        capture_output=True)
    check_or_die(cp)
    log(f"Extrait {i+1}/{len(timecodes)-1} créé.", LOG_SUCCESS)

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

extracts = sorted([f for f in os.listdir() if re.match(r"[0-9]+\.mp4", f) and f not in untouched])
log(f"{len(extracts)} extraits à caviarder...", LOG_INFO)
log(f"Commence le caviardage...", LOG_INFO)
for idx, extract in enumerate(extracts):
    cp = subprocess.run(["ffprobe", "-show_streams", extract], capture_output=True)
    check_or_die(cp)

    has_video = bool(re.search(r"codec_type=video", cp.stdout.decode("utf-8")))
    if has_video:
        cp = subprocess.run(["ffmpeg", "-i", extract, "-i", mask, "-filter_complex", "[1][0]scale2ref[i][v];[v][i]overlay", "-c:a", "copy", f"h{extract}"],
                            capture_output=True)
        check_or_die(cp)

        log(f"Extrait {idx+1}/{len(extracts)} caviardé.", LOG_SUCCESS)
    else:
        cp = subprocess.run(["ffmpeg", "-i", extract, "-i", mask, "-acodec", "copy", "-vcodec", "h264", f"h{extract}"],
                            capture_output=True)
        check_or_die(cp)

        log(f"Extrait {idx+1}/{len(extracts)} caviardé (le flux vidéo n'existait pas, et a été créé).", LOG_WARNING)

log("Renomme les extraits caviardés...", LOG_INFO)
for extract in extracts:
    os.rename(f"h{extract}", extract)
log("Extraits renommés.", LOG_SUCCESS)

extracts = sorted([f for f in os.listdir() if re.match(r"[0-9]+\.mp4", f)])
log(f"{len(extracts)} à sanitiser...", LOG_INFO)

for idx, extract in enumerate(extracts):
    cp = subprocess.run(["ffmpeg", "-i", extract, "-q", "0", "-max_muxing_queue_size", "1024", f"s{extract}"],
                        capture_output=True)
    check_or_die(cp)

    log(f"Extrait {idx+1}/{len(extracts)} sanitisé.", LOG_SUCCESS)

log("Renomme les extraits sanitisés...", LOG_INFO)
for extract in extracts:
    os.rename(f"s{extract}", extract)
log("Extraits renommés.", LOG_SUCCESS)

log("Commence la concaténation finale...", LOG_INFO)
concat_file = ""
for extract in sorted(extracts):
    concat_file += f"file '{extract}'\n"

with open("concat_file.txt", "w") as f:
    f.write(concat_file)

cp = subprocess.run(["ffmpeg", "-f", "concat", "-i", "concat_file.txt", "-c", "copy", "final.mp4"], capture_output=True)
check_or_die(cp)
log("Concaténation terminée.", LOG_SUCCESS)

log("Supprime les extraits et le fichier de concaténation...", LOG_INFO)
for extract in extracts:
    os.remove(extract)
os.remove("concat_file.txt")
log("Extraits et fichier de concaténation supprimés.", LOG_SUCCESS)

log("Terminé.", LOG_SUCCESS)