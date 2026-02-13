# Fonctions DMX à ajouter dans la classe MainWindow

def send_dmx_update(self):
    """Envoie les données DMX toutes les 40ms (25 FPS)"""
    if self.dmx.connected:
        self.dmx.update_from_projectors(self.projectors)
        self.dmx.send_dmx()

def show_dmx_wizard(self):
    """Assistant de configuration DMX simplifié"""
    wizard = QDialog(self)
    wizard.setWindowTitle("⚙️ Assistant de configuration DMX")
    wizard.setMinimumSize(600, 500)
    
    layout = QVBoxLayout(wizard)
    
    # Titre
    title = QLabel("🌐 Configuration du Node 2 Electroconcept")
    title.setFont(QFont("Segoe UI", 14, QFont.Bold))
    title.setAlignment(Qt.AlignCenter)
    layout.addWidget(title)
    
    layout.addSpacing(20)
    
    # Étape 1
    step1 = QLabel("📍 Étape 1: Configuration de votre PC")
    step1.setFont(QFont("Segoe UI", 12, QFont.Bold))
    layout.addWidget(step1)
    
    info1 = QLabel(
        "Votre PC doit avoir une IP fixe dans la plage 2.x.x.x\n"
        "IP recommandée: 2.0.0.100\n"
        "Masque: 255.0.0.0"
    )
    info1.setStyleSheet("padding: 10px; background: #1a1a1a; border-radius: 6px; color: #ccc;")
    layout.addWidget(info1)
    
    pc_ip_input = QLineEdit("2.0.0.100")
    pc_ip_input.setPlaceholderText("IP de votre PC")
    layout.addWidget(pc_ip_input)
    
    auto_config_pc = QPushButton("🔧 Configurer automatiquement mon PC")
    auto_config_pc.setStyleSheet("""
        QPushButton {
            background: #2a4a5a;
            color: white;
            padding: 10px;
            border-radius: 6px;
            font-weight: bold;
        }
        QPushButton:hover {
            background: #3a5a6a;
        }
    """)
    auto_config_pc.clicked.connect(lambda: self.auto_configure_pc_network(pc_ip_input.text()))
    layout.addWidget(auto_config_pc)
    
    layout.addSpacing(20)
    
    # Étape 2
    step2 = QLabel("🎛️ Étape 2: Configuration du Node 2")
    step2.setFont(QFont("Segoe UI", 12, QFont.Bold))
    layout.addWidget(step2)
    
    info2 = QLabel(
        "Le Node 2 doit avoir une IP fixe\n"
        "IP recommandée: 2.0.0.50\n"
        "Port Art-Net: 6454"
    )
    info2.setStyleSheet("padding: 10px; background: #1a1a1a; border-radius: 6px; color: #ccc;")
    layout.addWidget(info2)
    
    node_ip_input = QLineEdit("2.0.0.50")
    node_ip_input.setPlaceholderText("IP du Node 2")
    layout.addWidget(node_ip_input)
    
    test_btn = QPushButton("🧪 Tester la connexion")
    test_btn.setStyleSheet("""
        QPushButton {
            background: #2a5a2a;
            color: white;
            padding: 10px;
            border-radius: 6px;
            font-weight: bold;
        }
        QPushButton:hover {
            background: #3a6a3a;
        }
    """)
    test_btn.clicked.connect(lambda: self.test_dmx_connection(node_ip_input.text()))
    layout.addWidget(test_btn)
    
    layout.addSpacing(20)
    
    # Étape 3
    step3 = QLabel("✅ Étape 3: Valider et connecter")
    step3.setFont(QFont("Segoe UI", 12, QFont.Bold))
    layout.addWidget(step3)
    
    btn_layout = QHBoxLayout()
    
    ok_btn = QPushButton("✅ Connecter")
    ok_btn.clicked.connect(lambda: self.finalize_dmx_config(node_ip_input.text(), wizard))
    ok_btn.setStyleSheet("""
        QPushButton {
            background: #2a4a5a;
            color: white;
            padding: 12px 30px;
            border-radius: 6px;
            font-weight: bold;
            font-size: 14px;
        }
        QPushButton:hover {
            background: #3a5a6a;
        }
    """)
    btn_layout.addWidget(ok_btn)
    
    cancel_btn = QPushButton("❌ Annuler")
    cancel_btn.clicked.connect(wizard.reject)
    cancel_btn.setStyleSheet("""
        QPushButton {
            background: #3a3a3a;
            color: white;
            padding: 12px 30px;
            border-radius: 6px;
            font-size: 14px;
        }
        QPushButton:hover {
            background: #4a4a4a;
        }
    """)
    btn_layout.addWidget(cancel_btn)
    
    layout.addLayout(btn_layout)
    
    wizard.exec()

def auto_configure_pc_network(self, pc_ip):
    """Configure automatiquement l'IP du PC (Windows uniquement)"""
    import platform
    
    if platform.system() != "Windows":
        QMessageBox.warning(self, "Non supporté", 
            "La configuration automatique n'est disponible que sur Windows.\n"
            "Configurez manuellement votre carte réseau avec:\n"
            f"IP: {pc_ip}\n"
            "Masque: 255.0.0.0")
        return
    
    # Commande Windows pour configurer l'IP
    reply = QMessageBox.question(self, "Configuration automatique",
        f"Cette opération va configurer votre carte réseau avec:\n"
        f"IP: {pc_ip}\n"
        f"Masque: 255.0.0.0\n\n"
        f"⚠️ Nécessite les droits administrateur.\n"
        f"Continuer?",
        QMessageBox.Yes | QMessageBox.No)
    
    if reply == QMessageBox.Yes:
        try:
            import subprocess
            # Note: Nécessite l'exécution en admin
            cmd = f'netsh interface ip set address "Ethernet" static {pc_ip} 255.0.0.0'
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
            
            if result.returncode == 0:
                QMessageBox.information(self, "Succès", 
                    f"✅ IP configurée: {pc_ip}\n\n"
                    "Vous pouvez maintenant configurer le Node 2.")
            else:
                QMessageBox.critical(self, "Erreur",
                    f"❌ Erreur lors de la configuration:\n{result.stderr}\n\n"
                    "Exécutez le logiciel en tant qu'administrateur ou configurez manuellement.")
        except Exception as e:
            QMessageBox.critical(self, "Erreur", f"❌ Erreur: {e}")

def test_dmx_connection(self, node_ip):
    """Teste la connexion au Node 2"""
    try:
        # Ping simple
        import subprocess
        import platform
        
        param = '-n' if platform.system().lower() == 'windows' else '-c'
        command = ['ping', param, '1', node_ip]
        result = subprocess.run(command, capture_output=True, text=True, timeout=2)
        
        if result.returncode == 0:
            QMessageBox.information(self, "Test réussi",
                f"✅ Le Node 2 répond sur {node_ip} !\n\n"
                "Vous pouvez cliquer sur 'Connecter'.")
        else:
            QMessageBox.warning(self, "Test échoué",
                f"❌ Pas de réponse de {node_ip}\n\n"
                "Vérifiez:\n"
                "• Le câble Ethernet est branché\n"
                "• Le Node 2 est alimenté\n"
                "• Votre PC a l'IP 2.0.0.100\n"
                "• Le Node 2 a l'IP 2.0.0.50")
    except Exception as e:
        QMessageBox.critical(self, "Erreur", f"❌ Erreur de test: {e}")

def finalize_dmx_config(self, node_ip, dialog):
    """Finalise la configuration et connecte"""
    self.dmx.target_ip = node_ip
    
    if self.dmx.connect():
        QMessageBox.information(self, "Connexion réussie",
            f"✅ Connecté au Node 2 sur {node_ip} !\n\n"
            "Les lumières sont maintenant contrôlées en temps réel.")
        dialog.accept()
        self.update_status_indicators()
    else:
        QMessageBox.critical(self, "Erreur de connexion",
            "❌ Impossible de se connecter.\n\n"
            "Vérifiez la configuration réseau.")

def toggle_dmx_connection(self):
    """Connecte ou déconnecte le DMX"""
    if self.dmx.connected:
        self.dmx.disconnect()
        QMessageBox.information(self, "Déconnexion", "🔌 DMX déconnecté")
    else:
        if self.dmx.connect():
            QMessageBox.information(self, "Connexion", 
                f"✅ DMX connecté à {self.dmx.target_ip}")
        else:
            QMessageBox.critical(self, "Erreur", 
                "❌ Échec de connexion\n\nUtilisez l'assistant de configuration.")
    
    self.update_status_indicators()

def show_dmx_status(self):
    """Affiche l'état de la connexion DMX"""
    status = "✅ Connecté" if self.dmx.connected else "❌ Déconnecté"
    
    msg = f"État DMX / Art-Net\n\n"
    msg += f"Statut: {status}\n"
    msg += f"IP cible: {self.dmx.target_ip}\n"
    msg += f"Port: {self.dmx.target_port}\n"
    msg += f"Univers: {self.dmx.universe}\n"
    msg += f"FPS: 25 (envoi toutes les 40ms)"
    
    QMessageBox.information(self, "État DMX", msg)

def show_dmx_manual_config(self):
    """Configuration manuelle avancée"""
    dialog = QDialog(self)
    dialog.setWindowTitle("🔧 Configuration manuelle DMX")
    dialog.setMinimumWidth(400)
    
    layout = QVBoxLayout(dialog)
    
    # IP
    layout.addWidget(QLabel("IP du Node 2:"))
    ip_input = QLineEdit(self.dmx.target_ip)
    layout.addWidget(ip_input)
    
    # Port
    layout.addWidget(QLabel("Port Art-Net:"))
    port_input = QLineEdit(str(self.dmx.target_port))
    layout.addWidget(port_input)
    
    # Univers
    layout.addWidget(QLabel("Univers:"))
    universe_input = QLineEdit(str(self.dmx.universe))
    layout.addWidget(universe_input)
    
    # Boutons
    btn_layout = QHBoxLayout()
    
    ok_btn = QPushButton("✅ OK")
    ok_btn.clicked.connect(lambda: self.save_manual_dmx_config(
        ip_input.text(), 
        int(port_input.text()), 
        int(universe_input.text()),
        dialog
    ))
    btn_layout.addWidget(ok_btn)
    
    cancel_btn = QPushButton("❌ Annuler")
    cancel_btn.clicked.connect(dialog.reject)
    btn_layout.addWidget(cancel_btn)
    
    layout.addLayout(btn_layout)
    
    dialog.exec()

def save_manual_dmx_config(self, ip, port, universe, dialog):
    """Sauvegarde la configuration manuelle"""
    self.dmx.target_ip = ip
    self.dmx.target_port = port
    self.dmx.universe = universe
    
    QMessageBox.information(self, "Configuration sauvegardée",
        "✅ Configuration mise à jour\n\n"
        "Utilisez 'Connecter/Déconnecter' pour activer.")
    
    dialog.accept()

def update_status_indicators(self):
    """Met à jour les indicateurs de statut AKAI et DMX"""
    # Mettre à jour le label d'état
    if hasattr(self, 'status_label'):
        akai_status = "🎹 AKAI: ✅" if (MIDI_AVAILABLE and self.midi_handler.midi_in and self.midi_handler.midi_out) else "🎹 AKAI: ❌"
        dmx_status = "🌐 DMX: ✅" if self.dmx.connected else "🌐 DMX: ❌"
        
        self.status_label.setText(f"{akai_status}  |  {dmx_status}")
        
        # Couleur selon l'état
        if self.dmx.connected:
            self.status_label.setStyleSheet("color: #4aff4a; font-weight: bold; padding: 5px;")
        else:
            self.status_label.setStyleSheet("color: #ff4a4a; font-weight: bold; padding: 5px;")
