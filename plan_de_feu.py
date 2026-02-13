"""
Plan de Feu - Visualisation des projecteurs
"""
from PySide6.QtWidgets import (
    QFrame, QWidget, QVBoxLayout, QGridLayout, QHBoxLayout,
    QLabel, QMenu, QWidgetAction, QPushButton, QSlider, QRubberBand
)
from PySide6.QtCore import Qt, QTimer, QEvent, QRect, QPoint, QSize, Signal
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPen


class ColorPickerWidget(QWidget):
    """Gradient HSV cliquable/draggable - integre dans un menu contextuel"""

    colorSelected = Signal(QColor)

    def __init__(self, width=230, height=140, parent=None):
        super().__init__(parent)
        self.setFixedSize(width, height)
        self.setCursor(Qt.CrossCursor)
        self._image = None
        self._marker_pos = None
        self._generate_gradient()

    def _generate_gradient(self):
        """Genere le gradient HSV: hue horizontal, blanc en haut, noir en bas"""
        w, h = self.width(), self.height()
        self._image = QImage(w, h, QImage.Format_RGB32)
        mid = h / 2.0
        for x in range(w):
            hue = x / w
            for y in range(h):
                if y <= mid:
                    sat = y / mid if mid > 0 else 1.0
                    val = 1.0
                else:
                    sat = 1.0
                    val = (h - y) / mid if mid > 0 else 0.0
                color = QColor.fromHsvF(
                    min(hue, 1.0), min(sat, 1.0), min(val, 1.0)
                )
                self._image.setPixelColor(x, y, color)

    def paintEvent(self, event):
        if not self._image:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.drawImage(0, 0, self._image)
        # Marqueur de position
        if self._marker_pos:
            x, y = self._marker_pos
            pen = QPen(QColor("white"), 2)
            painter.setPen(pen)
            painter.drawEllipse(QPoint(x, y), 6, 6)
            pen.setColor(QColor("black"))
            pen.setWidth(1)
            painter.setPen(pen)
            painter.drawEllipse(QPoint(x, y), 7, 7)
        painter.end()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._pick_color(event.pos())

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.LeftButton:
            self._pick_color(event.pos())

    def _pick_color(self, pos):
        x = max(0, min(pos.x(), self.width() - 1))
        y = max(0, min(pos.y(), self.height() - 1))
        self._marker_pos = (x, y)
        color = QColor(self._image.pixelColor(x, y))
        self.colorSelected.emit(color)
        self.update()


class PlanDeFeu(QFrame):
    """Visualisation du plan de feu avec les projecteurs"""

    def __init__(self, projectors, main_window=None):
        super().__init__()
        self.projectors = projectors
        self.main_window = main_window
        self.lamps = []
        self.selected_lamps = set()  # set of (group, idx)
        self._rubber_band = None
        self._rubber_band_origin = None
        self._rubber_band_active = False

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignTop)
        layout.setContentsMargins(10, 30, 10, 10)

        title_layout = QHBoxLayout()
        title = QLabel("Lumieres")
        title.setFont(QFont("Segoe UI", 11, QFont.Bold))
        title_layout.addWidget(title)
        title_layout.addStretch()

        self.dmx_toggle_btn = QPushButton("ON")
        self.dmx_toggle_btn.setCheckable(True)
        self.dmx_toggle_btn.setChecked(True)
        self.dmx_toggle_btn.setFixedSize(50, 24)
        self.dmx_toggle_btn.setStyleSheet("""
            QPushButton {
                background: #228b22; color: white; border: none;
                border-radius: 12px; font-weight: bold; font-size: 10px;
            }
            QPushButton:!checked {
                background: #8b0000;
            }
        """)
        self.dmx_toggle_btn.clicked.connect(self._toggle_dmx_output)
        title_layout.addWidget(self.dmx_toggle_btn)

        layout.addLayout(title_layout)
        layout.addSpacing(15)

        grid = QGridLayout()
        grid.setSpacing(10)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(9, 1)

        # 6 projecteurs CONTRE (ligne 0)
        contre_positions = [2, 3, 4, 5, 6, 7]
        for i, col in enumerate(contre_positions):
            l = self._create_lamp("contre", i)
            grid.addWidget(l, 0, col, alignment=Qt.AlignCenter)
            self.lamps.append(("contre", i, l))

        grid.setRowMinimumHeight(1, 25)

        # 2 projecteurs LAT (ligne 2)
        lat_left = self._create_lamp("lat", 0)
        grid.addWidget(lat_left, 2, 1)
        self.lamps.append(("lat", 0, lat_left))

        lat_right = self._create_lamp("lat", 1)
        grid.addWidget(lat_right, 2, 8)
        self.lamps.append(("lat", 1, lat_right))

        grid.setRowMinimumHeight(3, 25)

        # 3 DOUCHES (ligne 4)
        douche_positions = [3, 5, 7]
        for i, col in enumerate(douche_positions):
            l = self._create_lamp(f"douche{i+1}", 0)
            grid.addWidget(l, 4, col, alignment=Qt.AlignCenter)
            self.lamps.append((f"douche{i+1}", 0, l))

        grid.setRowMinimumHeight(5, 25)

        # 4 FACE (ligne 6)
        face_positions = [2, 4, 6, 8]
        for i, col in enumerate(face_positions):
            l = self._create_lamp("face", i)
            grid.addWidget(l, 6, col, alignment=Qt.AlignCenter)
            self.lamps.append(("face", i, l))

        grid.setRowMinimumHeight(7, 25)

        # 1 PUBLIC (ligne 8)
        public_lamp = self._create_lamp("public", 0)
        grid.addWidget(public_lamp, 8, 4, alignment=Qt.AlignCenter)
        self.lamps.append(("public", 0, public_lamp))
        public_label = QLabel("Public")
        public_label.setStyleSheet("color: #888; font-size: 9px;")
        public_label.setAlignment(Qt.AlignCenter)
        grid.addWidget(public_label, 8, 5)

        # 1 FUMEE (ligne 8, a droite)
        fumee_lamp = self._create_lamp("fumee", 0)
        grid.addWidget(fumee_lamp, 8, 7, alignment=Qt.AlignCenter)
        self.lamps.append(("fumee", 0, fumee_lamp))
        fumee_label = QLabel("Fumee")
        fumee_label.setStyleSheet("color: #888; font-size: 9px;")
        fumee_label.setAlignment(Qt.AlignCenter)
        grid.addWidget(fumee_label, 8, 8)

        layout.addLayout(grid)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(60)

    # ── Creation des lampes ──────────────────────────────────────────

    def _create_lamp(self, group, idx):
        """Cree un QLabel lamp avec curseur main et event filter"""
        l = QLabel()
        l.setFixedSize(24, 24)
        l.setStyleSheet("background:#0a0a0a; border-radius:12px; border: 2px solid #2a2a2a;")
        l.setCursor(Qt.PointingHandCursor)
        l.setContextMenuPolicy(Qt.PreventContextMenu)
        l.setProperty("group", group)
        l.setProperty("idx", idx)
        l.installEventFilter(self)
        return l

    # ── Gestion des evenements souris ────────────────────────────────

    def eventFilter(self, obj, event):
        """Clic gauche = selection, clic droit = menu contextuel"""
        if event.type() == QEvent.Type.MouseButtonPress:
            group = obj.property("group")
            idx = obj.property("idx")
            if group is not None and idx is not None:
                key = (group, idx)

                if event.button() == Qt.LeftButton:
                    # Clic gauche: selection
                    if event.modifiers() & Qt.ControlModifier:
                        # Ctrl+clic: toggle dans la selection
                        if key in self.selected_lamps:
                            self.selected_lamps.discard(key)
                        else:
                            self.selected_lamps.add(key)
                    else:
                        # Clic simple: selectionner uniquement celui-ci
                        self.selected_lamps.clear()
                        self.selected_lamps.add(key)
                    self.refresh()
                    return True

                elif event.button() == Qt.RightButton:
                    # Clic droit: menu contextuel
                    if key not in self.selected_lamps:
                        self.selected_lamps.clear()
                        self.selected_lamps.add(key)
                        self.refresh()
                    self.show_color_menu(event.pos(), obj, group, idx)
                    return True

        return super().eventFilter(obj, event)

    def mousePressEvent(self, event):
        """Debut du rectangle de selection (clic gauche sur fond)"""
        if event.button() == Qt.LeftButton:
            self._rubber_band_origin = event.pos()
            self._rubber_band_active = False
            if not self._rubber_band:
                self._rubber_band = QRubberBand(QRubberBand.Shape.Rectangle, self)
            if not (event.modifiers() & Qt.ControlModifier):
                self.selected_lamps.clear()
                self.refresh()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        """Mise a jour du rectangle de selection"""
        if self._rubber_band_origin and (event.buttons() & Qt.LeftButton):
            if not self._rubber_band_active:
                # Seuil de 4px avant d'activer le rubber band
                delta = event.pos() - self._rubber_band_origin
                if abs(delta.x()) > 4 or abs(delta.y()) > 4:
                    self._rubber_band_active = True
                    self._rubber_band.setGeometry(
                        QRect(self._rubber_band_origin, QSize())
                    )
                    self._rubber_band.show()
            if self._rubber_band_active:
                rect = QRect(self._rubber_band_origin, event.pos()).normalized()
                self._rubber_band.setGeometry(rect)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        """Fin du rectangle de selection - selectionne les lampes dans la zone"""
        if event.button() == Qt.LeftButton:
            if self._rubber_band_active and self._rubber_band:
                rect = self._rubber_band.geometry()
                self._rubber_band.hide()
                for group, idx, lamp in self.lamps:
                    lamp_pos = lamp.mapTo(self, QPoint(0, 0))
                    lamp_rect = QRect(lamp_pos, lamp.size())
                    if rect.intersects(lamp_rect):
                        self.selected_lamps.add((group, idx))
                self.refresh()
            self._rubber_band_origin = None
            self._rubber_band_active = False
        super().mouseReleaseEvent(event)

    # ── Projecteurs cibles ───────────────────────────────────────────

    def _get_target_projectors(self, group, idx):
        """Retourne les projecteurs cibles (tous les selectionnes)"""
        targets = []
        for g, i in self.selected_lamps:
            projs = [p for p in self.projectors if p.group == g]
            if i < len(projs):
                targets.append((projs[i], g, i))
        if not targets:
            projs = [p for p in self.projectors if p.group == group]
            if idx < len(projs):
                targets.append((projs[idx], group, idx))
        return targets

    # ── DMX toggle ───────────────────────────────────────────────────

    def _toggle_dmx_output(self):
        if self.dmx_toggle_btn.isChecked():
            self.dmx_toggle_btn.setText("ON")
        else:
            self.dmx_toggle_btn.setText("OFF")

    def is_dmx_enabled(self):
        return self.dmx_toggle_btn.isChecked()

    # ── Menu contextuel (clic droit) ─────────────────────────────────

    def show_color_menu(self, pos, lamp, group, idx):
        """Menu contextuel avec info, color picker integre et fader dimmer"""
        targets = self._get_target_projectors(group, idx)
        if not targets:
            return

        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background: #1e1e1e;
                border: 1px solid #3a3a3a;
                border-radius: 6px;
                padding: 6px;
            }
            QMenu::separator {
                height: 1px;
                background: #3a3a3a;
                margin: 4px 8px;
            }
        """)

        # === INFO PROJECTEUR(S) ===
        if len(targets) == 1:
            proj, g, i = targets[0]
            proj_name = f"{g.capitalize()} {i + 1}" if g != "face" else "Face"
            dmx_info = ""
            if self.main_window and hasattr(self.main_window, 'artnet'):
                key = f"{g}{i}" if g != "face" else "face"
                if key in self.main_window.artnet.projector_channels:
                    channels = self.main_window.artnet.projector_channels[key]
                    if channels:
                        start = min(channels)
                        end = max(channels)
                        dmx_info = f"  |  DMX {start}-{end}"
            info_text = f"{proj_name}{dmx_info}"
        else:
            info_text = f"{len(targets)} projos selec."

        info_label = QLabel(info_text)
        info_label.setStyleSheet(
            "color: #00d4ff; font-weight: bold; font-size: 12px; padding: 4px 8px;"
        )
        info_label.setAlignment(Qt.AlignCenter)
        info_action = QWidgetAction(menu)
        info_action.setDefaultWidget(info_label)
        menu.addAction(info_action)

        menu.addSeparator()

        # === COLOR PICKER HSV ===
        picker_container = QWidget()
        picker_layout = QVBoxLayout(picker_container)
        picker_layout.setContentsMargins(4, 2, 4, 2)
        picker_layout.setSpacing(4)

        # Apercu couleur actuelle
        self._color_preview = QLabel()
        self._color_preview.setFixedHeight(18)
        current_color = targets[0][0].base_color
        self._color_preview.setStyleSheet(
            f"background: {current_color.name()}; border-radius: 4px; "
            f"border: 1px solid #555;"
        )
        picker_layout.addWidget(self._color_preview)

        # Gradient HSV
        picker = ColorPickerWidget(230, 200)
        picker.colorSelected.connect(
            lambda color, t=targets: self._apply_color_to_targets(t, color)
        )
        picker_layout.addWidget(picker)

        picker_action = QWidgetAction(menu)
        picker_action.setDefaultWidget(picker_container)
        menu.addAction(picker_action)

        menu.addSeparator()

        # === FADER DIMMER HORIZONTAL ===
        dimmer_widget = QWidget()
        dimmer_layout = QHBoxLayout(dimmer_widget)
        dimmer_layout.setContentsMargins(8, 4, 8, 4)
        dimmer_layout.setSpacing(8)

        dimmer_icon = QLabel("Dim")
        dimmer_icon.setStyleSheet("color: #888; font-size: 11px; font-weight: bold;")
        dimmer_layout.addWidget(dimmer_icon)

        dimmer_slider = QSlider(Qt.Horizontal)
        dimmer_slider.setRange(0, 100)
        dimmer_slider.setValue(targets[0][0].level)
        dimmer_slider.setFixedWidth(150)
        dimmer_slider.setStyleSheet("""
            QSlider::groove:horizontal {
                background: #333; height: 8px; border-radius: 4px;
            }
            QSlider::handle:horizontal {
                background: #00d4ff; width: 16px; height: 16px;
                margin: -4px 0; border-radius: 8px;
            }
            QSlider::sub-page:horizontal {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #005577, stop:1 #00d4ff);
                border-radius: 4px;
            }
        """)
        dimmer_slider.valueChanged.connect(
            lambda v, t=targets: self._set_dimmer_for_targets(t, v)
        )
        dimmer_layout.addWidget(dimmer_slider)

        self._dimmer_value_label = QLabel(f"{targets[0][0].level}%")
        self._dimmer_value_label.setStyleSheet(
            "color: #ddd; font-size: 12px; font-weight: bold; min-width: 35px;"
        )
        self._dimmer_value_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        dimmer_slider.valueChanged.connect(
            lambda v: self._dimmer_value_label.setText(f"{v}%")
        )
        dimmer_layout.addWidget(self._dimmer_value_label)

        dimmer_action = QWidgetAction(menu)
        dimmer_action.setDefaultWidget(dimmer_widget)
        menu.addAction(dimmer_action)

        menu.exec(lamp.mapToGlobal(pos))

    # ── Application couleur / dimmer ─────────────────────────────────

    def _apply_color_to_targets(self, targets, color):
        """Applique une couleur a tous les projecteurs cibles (temps reel)"""
        for proj, g, i in targets:
            proj.base_color = color
            if proj.level > 0:
                brightness = proj.level / 100.0
                proj.color = QColor(
                    int(color.red() * brightness),
                    int(color.green() * brightness),
                    int(color.blue() * brightness)
                )
            else:
                proj.color = QColor(0, 0, 0)

        # Mettre a jour l'apercu couleur dans le menu
        if hasattr(self, '_color_preview') and self._color_preview:
            self._color_preview.setStyleSheet(
                f"background: {color.name()}; border-radius: 4px; "
                f"border: 1px solid #555;"
            )

        # Envoyer DMX
        if self.main_window and hasattr(self.main_window, 'artnet') and self.main_window.artnet:
            self.main_window.artnet.update_from_projectors(self.projectors)

        self.refresh()

    def _set_dimmer_for_targets(self, targets, level):
        """Applique le dimmer a tous les projecteurs cibles"""
        for proj, g, i in targets:
            self.set_projector_dimmer(proj, level)

    def set_projector_dimmer(self, proj, level):
        """Change le dimmer d'un projecteur et met a jour DMX"""
        proj.level = level
        if level > 0:
            brightness = level / 100.0
            proj.color = QColor(
                int(proj.base_color.red() * brightness),
                int(proj.base_color.green() * brightness),
                int(proj.base_color.blue() * brightness)
            )
        else:
            proj.color = QColor(0, 0, 0)

        if self.main_window and hasattr(self.main_window, 'artnet') and self.main_window.artnet:
            self.main_window.artnet.update_from_projectors(self.projectors)

        self.refresh()

    # ── Compatibilite ────────────────────────────────────────────────

    def change_projector_color_only(self, group, idx, color):
        """Change la couleur d'un projecteur specifique"""
        projs = [p for p in self.projectors if p.group == group]
        if idx < len(projs):
            p = projs[idx]
            p.base_color = color
            if p.level > 0:
                brightness = p.level / 100.0
                p.color = QColor(
                    int(color.red() * brightness),
                    int(color.green() * brightness),
                    int(color.blue() * brightness)
                )
            else:
                p.color = QColor(0, 0, 0)

    def change_projector_color(self, group, idx, color, pad_row):
        """ANCIENNE VERSION - gardee pour compatibilite"""
        self.change_projector_color_only(group, idx, color)

    # ── Rafraichissement visuel ──────────────────────────────────────

    def refresh(self):
        """Rafraichit les lampes avec bordure de selection cyan"""
        for group, idx, lamp in self.lamps:
            projs = [p for p in self.projectors if p.group == group]
            if idx < len(projs):
                p = projs[idx]
                key = (group, idx)
                is_selected = key in self.selected_lamps

                if p.level > 0 and not p.muted:
                    if is_selected:
                        border = "3px solid #00d4ff"
                    else:
                        border = f"2px solid {p.color.lighter(150).name()}"
                    lamp.setStyleSheet(
                        f"background:{p.color.name()}; border-radius:12px; "
                        f"border: {border};"
                    )
                else:
                    if is_selected:
                        border = "3px solid #00d4ff"
                    else:
                        border = "2px solid #2a2a2a"
                    lamp.setStyleSheet(
                        f"background:#0a0a0a; border-radius:12px; border: {border};"
                    )


class PlanDeFeuPreview(QWidget):
    """Previsualisation du plan de feu sous la timeline"""

    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self.setFixedHeight(120)
        self.setStyleSheet("background: #0a0a0a; border-top: 2px solid #3a3a3a;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)

        title = QLabel("Plan de Feu - Previsualisation")
        title.setStyleSheet("color: white; font-weight: bold; font-size: 14px;")
        layout.addWidget(title)

        grid = QGridLayout()
        grid.setSpacing(5)

        self.projector_widgets = {}

        face_label = QLabel("Face:")
        face_label.setStyleSheet("color: #888; font-size: 11px;")
        grid.addWidget(face_label, 0, 0)
        self.face_widget = QLabel("O")
        self.face_widget.setFixedSize(40, 40)
        self.face_widget.setAlignment(Qt.AlignCenter)
        self.face_widget.setStyleSheet("background: #1a1a1a; border-radius: 20px; font-size: 20px;")
        grid.addWidget(self.face_widget, 0, 1)

        for i in range(3):
            douche_label = QLabel(f"Douche {i+1}:")
            douche_label.setStyleSheet("color: #888; font-size: 11px;")
            grid.addWidget(douche_label, 0, 2 + i*2)
            widget = QLabel("O")
            widget.setFixedSize(40, 40)
            widget.setAlignment(Qt.AlignCenter)
            widget.setStyleSheet("background: #1a1a1a; border-radius: 20px; font-size: 20px;")
            grid.addWidget(widget, 0, 3 + i*2)
            self.projector_widgets[f'douche{i+1}'] = widget

        contres_label = QLabel("Contres:")
        contres_label.setStyleSheet("color: #888; font-size: 11px;")
        grid.addWidget(contres_label, 0, 8)
        self.contres_widget = QLabel("O")
        self.contres_widget.setFixedSize(40, 40)
        self.contres_widget.setAlignment(Qt.AlignCenter)
        self.contres_widget.setStyleSheet("background: #1a1a1a; border-radius: 20px; font-size: 20px;")
        grid.addWidget(self.contres_widget, 0, 9)

        layout.addLayout(grid)

        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self.update_preview)
        self.update_timer.start(50)

    def update_preview(self):
        if not self.main_window or not hasattr(self.main_window, 'projectors'):
            return

        for proj in self.main_window.projectors:
            widget = None

            if proj.group == "face":
                widget = self.face_widget
            elif proj.group == "contre":
                pass
            elif proj.group == "douche":
                widget = self.projector_widgets.get(f'douche{proj.index + 1}')

            if widget and proj.level > 0:
                color = proj.color
                widget.setStyleSheet(f"""
                    background: {color.name()};
                    border-radius: 20px;
                    font-size: 20px;
                """)
            elif widget:
                widget.setStyleSheet("""
                    background: #1a1a1a;
                    border-radius: 20px;
                    font-size: 20px;
                """)
