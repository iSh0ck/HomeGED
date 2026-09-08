"""
Double authentification : l'algorithme lui-même.

Réimplémenter de la cryptographie n'est défendable que vérifié. Ces tests
rejouent les vecteurs officiels de la RFC 6238 (annexe B) : si la formule
dérive d'un chiffre, ils tombent.
"""

from app import otp


# RFC 6238, annexe B : secret ASCII « 12345678901234567890 », SHA-1, 8 chiffres.
# On compare ici les 6 derniers chiffres, longueur retenue par l'application.
SECRET_RFC = otp.base64.b32encode(b"12345678901234567890").decode()

VECTEURS = [
    (59, "94287082"),
    (1111111109, "07081804"),
    (1111111111, "14050471"),
    (1234567890, "89005924"),
    (2000000000, "69279037"),
    (20000000000, "65353130"),
]


def test_vecteurs_officiels_rfc6238():
    for instant, attendu in VECTEURS:
        assert otp.code(SECRET_RFC, instant) == attendu[-6:], f"instant {instant}"


def test_tolerance_dun_pas_de_part_et_dautre():
    """Le téléphone et le serveur n'ont jamais tout à fait la même heure."""
    instant = 1111111111
    assert otp.verifier(SECRET_RFC, otp.code(SECRET_RFC, instant - 30), instant)
    assert otp.verifier(SECRET_RFC, otp.code(SECRET_RFC, instant + 30), instant)
    # au-delà, non : un code intercepté ne doit pas vivre indéfiniment
    assert not otp.verifier(SECRET_RFC, otp.code(SECRET_RFC, instant + 90), instant)


def test_codes_mal_formes_refuses():
    instant = 1111111111
    for propose in ("", None, "abcdef", "1234", "1234567", "  "):
        assert not otp.verifier(SECRET_RFC, propose, instant)


def test_secret_tire_au_sort_est_utilisable():
    secret = otp.nouveau_secret()
    assert len(secret) == 32
    assert set(secret) <= set(otp.ALPHABET)
    assert otp.verifier(secret, otp.code(secret))
    assert otp.nouveau_secret() != secret


def test_uri_de_provisionnement_est_lisible_par_une_application():
    uri = otp.uri_provisionnement("ABCDEFGH", "marie@foyer.fr")
    assert uri.startswith("otpauth://totp/HomeGED%3Amarie%40foyer.fr?")
    assert "secret=ABCDEFGH" in uri and "issuer=HomeGED" in uri
    assert "digits=6" in uri and "period=30" in uri


def test_code_de_secours_ne_sert_quune_fois():
    clairs, stockes = otp.nouveaux_codes_secours()
    assert len(clairs) == otp.NOMBRE_CODES_SECOURS
    assert otp.nombre_codes_secours(stockes) == otp.NOMBRE_CODES_SECOURS
    # aucun code en clair ne se retrouve dans ce qui est stocké
    assert all(code not in stockes for code in clairs)

    restant = otp.consommer_code_secours(stockes, clairs[0])
    assert restant is not None
    assert otp.nombre_codes_secours(restant) == otp.NOMBRE_CODES_SECOURS - 1
    # le même code ne passe plus
    assert otp.consommer_code_secours(restant, clairs[0]) is None
    # les autres, si
    assert otp.consommer_code_secours(restant, clairs[1]) is not None


def test_code_de_secours_inconnu_refuse():
    _, stockes = otp.nouveaux_codes_secours()
    assert otp.consommer_code_secours(stockes, "ZZZZZ-ZZZZZ") is None
    assert otp.consommer_code_secours(None, "ZZZZZ-ZZZZZ") is None
    assert otp.consommer_code_secours("pas du json", "ZZZZZ-ZZZZZ") is None
