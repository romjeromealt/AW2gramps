#!/usr/bin/env python3
"""
Tests unitaires pour script_ocr.py
Utilise unittest.mock pour simuler les dépendances externes (pytesseract, cv2, etc.)
"""

import unittest
from unittest.mock import patch, MagicMock, mock_open
import os
import sys
import json
import numpy as np
import tempfile

# Ajouter le répertoire courant au path pour importer script_ocr
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Mock sys.argv pour éviter que argparse ne bloque l'import
sys.argv = ['script_ocr.py']

# Importer les fonctions à tester depuis script_ocr
from script_ocr import (
    phonex_fr,
    compare_phonex,
    tesseract_ocr_raw,
    charger_dictionnaire_noms,
    sauvegader_dictionnaire_noms,
    corriger_nom,
    detect_columns,
    load_profile,
    DEFAULT_PROFILES,
)


class TestPhonexAlgorithm(unittest.TestCase):
    """Tests pour l'algorithme Phonex (phonétique)"""

    def test_phonex_fr_none(self):
        """Test avec une entrée None"""
        self.assertEqual(phonex_fr(None), "Z000")

    def test_phonex_fr_empty(self):
        """Test avec une chaîne vide"""
        self.assertEqual(phonex_fr(""), "Z000")

    def test_phonex_fr_returns_string(self):
        """Test que phonex_fr retourne toujours une chaîne de 4 caractères"""
        result = phonex_fr("Test")
        self.assertIsInstance(result, str)
        self.assertEqual(len(result), 4)

    def test_phonex_fr_uppercase(self):
        """Test que phonex_fr convertit en majuscules"""
        self.assertEqual(phonex_fr("test"), phonex_fr("TEST"))

    def test_compare_phonex_same_input(self):
        """Test que compare_phonex retourne True pour la même entrée"""
        self.assertTrue(compare_phonex("MARTIN", "MARTIN"))


class TestTesseractOCR(unittest.TestCase):
    """Tests pour la fonction tesseract_ocr_raw (avec mocks)"""

    @patch('subprocess.run')
    def test_tesseract_ocr_raw_success(self, mock_run):
        """Test de tesseract_ocr_raw avec une sortie réussie"""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "Texte extrait\n"
        mock_result.stderr = ""
        mock_run.return_value = mock_result

        result = tesseract_ocr_raw("fake_image.png", lang="fra", psm=6)
        self.assertEqual(result, "Texte extrait")

    @patch('subprocess.run')
    def test_tesseract_ocr_raw_failure(self, mock_run):
        """Test de tesseract_ocr_raw avec une erreur"""
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = "Erreur Tesseract"
        mock_run.return_value = mock_result

        result = tesseract_ocr_raw("fake_image.png", lang="fra", psm=6)
        self.assertEqual(result, "")

    @patch('subprocess.run')
    @patch('script_ocr.cv2.imwrite')
    @patch('script_ocr.os.path.exists')
    def test_tesseract_ocr_raw_with_numpy_array(self, mock_exists, mock_imwrite, mock_run):
        """Test de tesseract_ocr_raw avec un tableau numpy"""
        mock_exists.return_value = True
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "12345"
        mock_result.stderr = ""
        mock_run.return_value = mock_result

        fake_image = np.zeros((10, 10, 3), dtype=np.uint8)
        result = tesseract_ocr_raw(fake_image, lang="fra", psm=6, digits_only=True)
        self.assertEqual(result, "12345")


class TestDictionnaireNoms(unittest.TestCase):
    """Tests pour la gestion du dictionnaire de noms"""

    def setUp(self):
        """Créer un dictionnaire temporaire pour les tests"""
        self.temp_dict_path = tempfile.NamedTemporaryFile(
            mode='w', suffix='.json', delete=False
        ).name
        self.sample_dict = {
            "DUBOIS": ["DUBOIS", "DU BOIS", "DUBOIS"],
            "MARTIN": ["MARTIN", "MARTAIN"],
        }
        with open(self.temp_dict_path, 'w', encoding='utf-8') as f:
            json.dump(self.sample_dict, f)

    def tearDown(self):
        """Nettoyer le fichier temporaire"""
        if os.path.exists(self.temp_dict_path):
            os.unlink(self.temp_dict_path)

    def test_charger_dictionnaire_noms_success(self):
        """Test du chargement d'un dictionnaire valide"""
        result = charger_dictionnaire_noms(self.temp_dict_path)
        self.assertEqual(result, self.sample_dict)

    def test_charger_dictionnaire_noms_file_not_found(self):
        """Test du chargement d'un dictionnaire inexistant"""
        result = charger_dictionnaire_noms("nonexistent_file.json")
        self.assertEqual(result, {})

    def test_charger_dictionnaire_noms_invalid_json(self):
        """Test du chargement d'un fichier JSON invalide"""
        invalid_path = tempfile.NamedTemporaryFile(
            mode='w', suffix='.json', delete=False
        ).name
        with open(invalid_path, 'w') as f:
            f.write("{ invalid json }")

        result = charger_dictionnaire_noms(invalid_path)
        self.assertEqual(result, {})

        os.unlink(invalid_path)

    def test_sauvegader_dictionnaire_noms(self):
        """Test de la sauvegarde d'un dictionnaire"""
        test_dict = {"TEST": ["TEST", "TÈST"]}
        test_path = tempfile.NamedTemporaryFile(
            mode='w', suffix='.json', delete=False
        ).name

        sauvegader_dictionnaire_noms(test_dict, test_path)

        with open(test_path, 'r', encoding='utf-8') as f:
            loaded_dict = json.load(f)
        self.assertEqual(loaded_dict, test_dict)

        os.unlink(test_path)

    def test_corriger_nom_exact_match(self):
        """Test de la correction d'un nom avec correspondance exacte"""
        result = corriger_nom("DUBOIS", {"DUBOIS": ["DUBOIS", "DU BOIS"]})
        self.assertEqual(result, "DUBOIS")

    def test_corriger_nom_variante(self):
        """Test de la correction d'un nom avec une variante"""
        result = corriger_nom("DU BOIS", {"DUBOIS": ["DUBOIS", "DU BOIS"]})
        self.assertEqual(result, "DUBOIS")

    def test_corriger_nom_no_match(self):
        """Test de la correction d'un nom sans correspondance"""
        result = corriger_nom("INCONNU", {"DUBOIS": ["DUBOIS"]})
        self.assertEqual(result, "INCONNU")


class TestImageProcessing(unittest.TestCase):
    """Tests pour le traitement d'images (avec mocks pour cv2)"""

    @patch('script_ocr.cv2.cvtColor')
    @patch('script_ocr.cv2.Canny')
    @patch('script_ocr.cv2.HoughLinesP')
    def test_detect_columns_with_vertical_lines(self, mock_hough, mock_canny, mock_cvtcolor):
        """Test de la détection de colonnes avec des lignes verticales"""
        fake_img = np.zeros((100, 100, 3), dtype=np.uint8)
        mock_cvtcolor.return_value = np.zeros((100, 100), dtype=np.uint8)
        mock_canny.return_value = np.zeros((100, 100), dtype=np.uint8)
        mock_hough.return_value = np.array([
            [[10, 0, 10, 100]],
            [[50, 0, 50, 100]],
            [[90, 0, 90, 100]],
        ])

        result = detect_columns(fake_img)
        self.assertIn(10, result)
        self.assertIn(50, result)
        self.assertIn(90, result)

    @patch('script_ocr.cv2.cvtColor')
    @patch('script_ocr.cv2.Canny')
    @patch('script_ocr.cv2.HoughLinesP')
    def test_detect_columns_no_lines(self, mock_hough, mock_canny, mock_cvtcolor):
        """Test de la détection de colonnes sans lignes verticales"""
        fake_img = np.zeros((100, 100, 3), dtype=np.uint8)
        mock_cvtcolor.return_value = np.zeros((100, 100), dtype=np.uint8)
        mock_canny.return_value = np.zeros((100, 100), dtype=np.uint8)
        mock_hough.return_value = None

        result = detect_columns(fake_img)
        self.assertEqual(result, [])


class TestProfileManagement(unittest.TestCase):
    """Tests pour la gestion des profils"""

    def test_load_profile_default(self):
        """Test du chargement du profil par défaut"""
        result = load_profile("default")
        self.assertEqual(result["name"], DEFAULT_PROFILES["default"]["name"])

    def test_load_profile_nonexistent(self):
        """Test du chargement d'un profil inexistant (doit retourner default)"""
        result = load_profile("nonexistent_profile")
        self.assertEqual(result["name"], DEFAULT_PROFILES["default"]["name"])

    def test_load_profile_custom(self):
        """Test du chargement d'un profil personnalisé depuis un fichier"""
        profile_data = {
            "name": "Test Profile",
            "d": 5,
            "sigmaColor": 50,
            "columns": [{"type": "text", "is_name": True}],
        }
        profile_path = tempfile.NamedTemporaryFile(
            mode='w', suffix='.json', delete=False
        ).name
        with open(profile_path, 'w') as f:
            json.dump(profile_data, f)

        with patch('script_ocr.CONFIG_DIR', os.path.dirname(profile_path)):
            result = load_profile(os.path.basename(profile_path).replace('.json', ''))
            self.assertEqual(result["name"], "Test Profile")

        os.unlink(profile_path)


if __name__ == '__main__':
    unittest.main()
