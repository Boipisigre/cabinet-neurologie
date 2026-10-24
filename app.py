"""
app.py
------
Application Flask du cabinet.

Pages disponibles :
    /              -> redirige vers la liste des patients
    /patients      -> liste des patients
    /patients/<id> -> fiche d'un patient et de ses rendez-vous
    /rendez-vous   -> liste des rendez-vous, avec le nom du patient concerné
    /rendez-vous/nouveau -> formulaire de prise de rendez-vous
    /consultations -> liste des comptes-rendus de consultation

Chaque page affiche un menu permettant de passer de l'une à l'autre.

Pour la lancer (depuis la racine du projet, avec (venv) actif) :
    python3 app.py
"""

import sqlite3
from datetime import datetime

from flask import Flask, redirect, request
from markupsafe import escape

app = Flask(__name__)

# Les pages du menu, dans l'ordre d'affichage : (adresse, libellé)
PAGES = [
    ("/patients", "Patients"),
    ("/rendez-vous", "Rendez-vous"),
    ("/consultations", "Consultations"),
]


def se_connecter_a_la_base():
    connexion = sqlite3.connect("database/cabinet.db")
    connexion.row_factory = sqlite3.Row
    return connexion


def menu():
    """Construit le menu de navigation, avec la page courante mise en évidence."""
    liens = ""
    for adresse, libelle in PAGES:
        classe = ' class="actif"' if request.path == adresse else ""
        liens += f'<li><a href="{adresse}"{classe}>{libelle}</a></li>'
    return f"<nav><ul>{liens}</ul></nav>"


def page(titre, contenu):
    """Enveloppe le contenu d'une page dans le HTML commun (menu + titre)."""
    return f"""<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="utf-8">
    <title>{titre} — Cabinet de neurologie</title>
    <style>
        body {{ font-family: sans-serif; margin: 0; }}
        nav {{ background: #f4f4f4; border-bottom: 1px solid #ccc; padding: 10px 20px; }}
        nav ul {{ list-style: none; margin: 0; padding: 0; }}
        nav li {{ display: inline-block; margin-right: 15px; }}
        nav a {{ text-decoration: none; color: #333; }}
        nav a.actif {{ font-weight: bold; color: #0066cc; }}
        main {{ padding: 20px; }}
    </style>
</head>
<body>
{menu()}
<main>
<h1>{titre}</h1>
{contenu}
</main>
</body>
</html>"""


@app.route("/")
def accueil():
    # La racine n'a pas de contenu propre : on renvoie vers la première page.
    return redirect("/patients")


@app.route("/patients")
def liste_patients():
    connexion = se_connecter_a_la_base()
    curseur = connexion.cursor()

    curseur.execute("SELECT * FROM patients ORDER BY nom")
    patients = curseur.fetchall()

    connexion.close()

    html = "<ul>"
    for patient in patients:
        html += (
            f'<li><a href="/patients/{patient["id"]}">'
            f"{patient['prenom']} {patient['nom']}</a> — "
            f"né(e) le {patient['date_naissance']}</li>"
        )
    html += "</ul>"

    return page("Liste des patients", html)


@app.route("/patients/<int:patient_id>")
def fiche_patient(patient_id):
    connexion = se_connecter_a_la_base()
    curseur = connexion.cursor()

    # fetchone() renvoie None si aucun patient ne porte cet identifiant.
    curseur.execute("SELECT * FROM patients WHERE id = ?", (patient_id,))
    patient = curseur.fetchone()

    if patient is None:
        connexion.close()
        return page(
            "Patient introuvable",
            "<p>Aucun patient ne correspond à cet identifiant.</p>",
        ), 404

    # On ne garde que les rendez-vous de ce patient, du plus ancien au plus récent.
    curseur.execute("""
        SELECT date_rdv, heure_rdv, motif, statut
        FROM rendez_vous
        WHERE patient_id = ?
        ORDER BY date_rdv, heure_rdv
    """, (patient_id,))
    rendez_vous = curseur.fetchall()

    connexion.close()

    html = (
        f"<p><strong>Né(e) le :</strong> {patient['date_naissance']}<br>"
        f"<strong>Téléphone :</strong> {patient['telephone']}<br>"
        f"<strong>Email :</strong> {patient['email']}</p>"
        f'<p><a href="/rendez-vous/nouveau?patient_id={patient["id"]}">'
        "Prendre un rendez-vous pour ce patient</a></p>"
    )

    if rendez_vous:
        html += "<h2>Rendez-vous</h2><ul>"
        for rdv in rendez_vous:
            html += (
                f"<li>{rdv['date_rdv']} à {rdv['heure_rdv']} — "
                f"{escape(rdv['motif'] or '')} <em>({rdv['statut']})</em></li>"
            )
        html += "</ul>"
    else:
        html += "<p>Aucun rendez-vous enregistré pour ce patient.</p>"

    return page(f"{patient['prenom']} {patient['nom']}", html)


@app.route("/rendez-vous/nouveau", methods=["GET", "POST"])
def nouveau_rendez_vous():
    connexion = se_connecter_a_la_base()
    curseur = connexion.cursor()

    curseur.execute("SELECT id, nom, prenom FROM patients ORDER BY nom")
    patients = curseur.fetchall()

    # Valeurs du formulaire : vides en GET, conservées pour le réaffichage
    # en cas d'erreur. request.values lit aussi bien l'URL que le formulaire.
    patient_id = request.values.get("patient_id", "")
    date_rdv = request.values.get("date_rdv", "")
    heure_rdv = request.values.get("heure_rdv", "")
    motif = request.values.get("motif", "")

    erreur = None

    if request.method == "POST":
        try:
            patient_id_int = int(patient_id)
        except ValueError:
            patient_id_int = None

        patient_existe = any(p["id"] == patient_id_int for p in patients)

        try:
            datetime.strptime(date_rdv, "%Y-%m-%d")
            datetime.strptime(heure_rdv, "%H:%M")
        except ValueError:
            dates_valides = False
        else:
            dates_valides = True

        if not patient_existe:
            erreur = "Merci de choisir un patient."
        elif not dates_valides:
            erreur = "Merci de saisir une date et une heure valides."
        else:
            curseur.execute(
                "INSERT INTO rendez_vous (patient_id, date_rdv, heure_rdv, motif, statut) "
                "VALUES (?, ?, ?, ?, 'prévu')",
                (patient_id_int, date_rdv, heure_rdv, motif.strip() or None),
            )
            connexion.commit()
            connexion.close()
            # On renvoie vers la fiche du patient : le nouveau RDV y apparaît.
            return redirect(f"/patients/{patient_id_int}")

    # Liste déroulante des patients, avec celui déjà choisi s'il y en a un.
    options = ""
    for p in patients:
        selection = " selected" if str(p["id"]) == patient_id else ""
        options += (
            f'<option value="{p["id"]}"{selection}>'
            f"{escape(p['prenom'])} {escape(p['nom'])}</option>"
        )

    formulaire = f"""
<form method="post" action="/rendez-vous/nouveau">
    <p>
        <label for="patient_id">Patient</label><br>
        <select id="patient_id" name="patient_id" required>
            <option value="">— choisir un patient —</option>
            {options}
        </select>
    </p>
    <p>
        <label for="date_rdv">Date</label><br>
        <input type="date" id="date_rdv" name="date_rdv" value="{escape(date_rdv)}" required>
    </p>
    <p>
        <label for="heure_rdv">Heure</label><br>
        <input type="time" id="heure_rdv" name="heure_rdv" value="{escape(heure_rdv)}" required>
    </p>
    <p>
        <label for="motif">Motif (facultatif)</label><br>
        <input type="text" id="motif" name="motif" value="{escape(motif)}">
    </p>
    <button type="submit">Enregistrer le rendez-vous</button>
</form>
"""

    if erreur:
        formulaire = (
            f'<p style="color: #b00020;"><strong>{escape(erreur)}</strong></p>'
            + formulaire
        )

    connexion.close()
    return page("Prendre un rendez-vous", formulaire)


@app.route("/rendez-vous")
def liste_rendez_vous():
    connexion = se_connecter_a_la_base()
    curseur = connexion.cursor()

    curseur.execute("""
        SELECT
            r.date_rdv,
            r.heure_rdv,
            r.motif,
            r.statut,
            p.nom,
            p.prenom
        FROM rendez_vous AS r
        JOIN patients AS p ON r.patient_id = p.id
        ORDER BY r.date_rdv, r.heure_rdv
    """)
    rendez_vous = curseur.fetchall()

    connexion.close()

    html = '<p><a href="/rendez-vous/nouveau">Prendre un rendez-vous</a></p><ul>'
    for rdv in rendez_vous:
        html += (
            f"<li>{rdv['date_rdv']} à {rdv['heure_rdv']} — "
            f"{rdv['prenom']} {rdv['nom']} — {escape(rdv['motif'] or '')} "
            f"<em>({rdv['statut']})</em></li>"
        )
    html += "</ul>"

    return page("Liste des rendez-vous", html)


@app.route("/consultations")
def liste_consultations():
    connexion = se_connecter_a_la_base()
    curseur = connexion.cursor()

    # Même principe de jointure que pour les rendez-vous : on relie
    # "consultations" à "patients" via consultations.patient_id = patients.id
    curseur.execute("""
        SELECT
            c.date_consultation,
            c.motif,
            c.observations,
            c.diagnostic,
            c.traitement,
            c.medecin,
            p.nom,
            p.prenom
        FROM consultations AS c
        JOIN patients AS p ON c.patient_id = p.id
        ORDER BY c.date_consultation
    """)
    consultations = curseur.fetchall()

    connexion.close()

    # Ici on affiche un peu plus d'informations par consultation,
    # donc on construit un petit bloc par compte-rendu plutôt qu'une simple ligne.
    html = ""
    for c in consultations:
        html += "<div style='margin-bottom: 20px; padding-bottom: 10px; border-bottom: 1px solid #ccc;'>"
        html += f"<h3>{c['prenom']} {c['nom']} — {c['date_consultation']}</h3>"
        html += f"<p><strong>Motif :</strong> {c['motif']}</p>"
        html += f"<p><strong>Observations :</strong> {c['observations']}</p>"
        html += f"<p><strong>Diagnostic :</strong> {c['diagnostic']}</p>"
        html += f"<p><strong>Traitement :</strong> {c['traitement']}</p>"
        html += f"<p><strong>Médecin :</strong> {c['medecin']}</p>"
        html += "</div>"

    return page("Comptes-rendus de consultation", html)


if __name__ == "__main__":
    app.run(debug=True)
