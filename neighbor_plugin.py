import os
from qgis.PyQt.QtWidgets import (QAction, QDialog, QVBoxLayout, QHBoxLayout, 
                                 QLabel, QPushButton, QColorDialog, QDialogButtonBox, 
                                 QComboBox, QFormLayout, QMessageBox, QToolBar, QMenu)
from qgis.PyQt.QtGui import QColor, QIcon
from qgis.PyQt.QtCore import Qt
from qgis.core import QgsWkbTypes, QgsSettings, Qgis
from qgis.gui import QgsMapTool, QgsHighlight, QgsRubberBand, QgsMapToolIdentify


class NeighborHighlightPlugin:
    def __init__(self, iface):
        self.iface = iface
        self.action = None
        self.action_settings = None
        self.toolbar = None
        self.map_tool = None
        self.canvas = iface.mapCanvas()
        
        self.settings = QgsSettings()
        if not self.settings.contains("NeighborHighlight/main_color"):
            self.settings.setValue("NeighborHighlight/main_color", "#ff0000")
            self.settings.setValue("NeighborHighlight/neighbor_color", "#0000ff")
            self.settings.setValue("NeighborHighlight/line_color", "#ffa500")
            self.settings.setValue("NeighborHighlight/main_field", "")
            self.settings.setValue("NeighborHighlight/neigh_field", "")

    def initGui(self):
        plugin_dir = os.path.dirname(__file__)
        icon_path = os.path.join(plugin_dir, 'icon.png')
        icon = QIcon(icon_path)
        if icon.isNull():
            icon = QIcon.fromTheme("mActionIdentify", QIcon(":/images/themes/default/mActionIdentify.svg"))
            
        self.action = QAction(icon, "查询邻区关系", self.iface.mainWindow())
        self.action.setCheckable(True)
        self.action.triggered.connect(self.run)
        
        icon_settings = QIcon.fromTheme("mActionOptions", QIcon(":/images/themes/default/mActionOptions.svg"))
        self.action_settings = QAction(icon_settings, "参数配置", self.iface.mainWindow())
        self.action_settings.triggered.connect(self.show_settings_dialog)
        
        self.toolbar = QToolBar("邻区高亮工具")
        self.toolbar.setObjectName("NeighborHighlightToolbar")
        self.toolbar.addAction(self.action)
        self.toolbar.addAction(self.action_settings)
        
        self.iface.mainWindow().addToolBar(self.toolbar)
        self.iface.addPluginToMenu("&邻区工具", self.action)
        self.iface.addPluginToMenu("&邻区工具", self.action_settings)

    def unload(self):
        self.iface.removePluginMenu("&邻区工具", self.action)
        self.iface.removePluginMenu("&邻区工具", self.action_settings)
        
        if self.toolbar:
            self.iface.mainWindow().removeToolBar(self.toolbar)
            self.toolbar.deleteLater()
            self.toolbar = None
            
        self.clean_canvas()

    def run(self):
        main_f = self.settings.value("NeighborHighlight/main_field")
        neigh_f = self.settings.value("NeighborHighlight/neigh_field")
        if not main_f or not neigh_f:
            self.iface.messageBar().pushWarning("提示", "首次使用请先配置字段参数！")
            self.show_settings_dialog()
            self.action.setChecked(False)
            return

        if not self.map_tool:
            self.map_tool = NeighborMapTool(self.iface, self)
        self.canvas.setMapTool(self.map_tool)

    def clean_canvas(self):
        if hasattr(self, 'main_highlight') and self.main_highlight:
            self.canvas.scene().removeItem(self.main_highlight)
            self.main_highlight = None
            
        if hasattr(self, 'neighbor_highlights') and self.neighbor_highlights:
            for h in self.neighbor_highlights:
                self.canvas.scene().removeItem(h)
            self.neighbor_highlights = []
            
        if hasattr(self, 'rubberband') and self.rubberband:
            self.canvas.scene().removeItem(self.rubberband)
            self.rubberband = None
            
        if self.iface.activeLayer():
            self.iface.activeLayer().removeSelection()

    def show_settings_dialog(self):
        # （配置界面的代码保持不变）
        dialog = QDialog(self.iface.mainWindow())
        dialog.setWindowTitle("邻区工具 - 参数配置")
        dialog.setMinimumWidth(350)
        layout = QVBoxLayout(dialog)

        layer = self.iface.activeLayer()
        if not layer:
            QMessageBox.warning(dialog, "警告", "请先在地图上选择一个图层！")
            return
        
        field_names = [f.name() for f in layer.fields()]
        if not field_names:
            QMessageBox.warning(dialog, "警告", "当前图层没有属性字段！")
            return

        form_layout = QFormLayout()
        combo_main_field = QComboBox()
        combo_neigh_field = QComboBox()
        combo_main_field.addItems(field_names)
        combo_neigh_field.addItems(field_names)
        
        saved_main = self.settings.value("NeighborHighlight/main_field", "")
        saved_neigh = self.settings.value("NeighborHighlight/neigh_field", "")
        
        if saved_main in field_names: combo_main_field.setCurrentText(saved_main)
        elif "eci" in [f.lower() for f in field_names]:
            combo_main_field.setCurrentIndex([f.lower() for f in field_names].index("eci"))
            
        if saved_neigh in field_names: combo_neigh_field.setCurrentText(saved_neigh)
        elif "nci" in [f.lower() for f in field_names]:
            combo_neigh_field.setCurrentIndex([f.lower() for f in field_names].index("nci"))

        form_layout.addRow("主小区ID字段:", combo_main_field)
        form_layout.addRow("邻区列表字段:", combo_neigh_field)
        layout.addLayout(form_layout)
        
        tip_label = QLabel("提示：邻区列表字段中的多个ID需用竖线 '|' 分隔")
        tip_label.setStyleSheet("color: gray; font-size: 11px;")
        layout.addWidget(tip_label)
        layout.addSpacing(10)

        def create_color_row(label_text, current_color):
            row = QHBoxLayout()
            lbl = QLabel(label_text)
            btn = QPushButton()
            btn.setFixedSize(60, 25)
            btn.setStyleSheet(f"background-color: {current_color.name()}; border: 1px solid gray;")
            
            def pick_color():
                color = QColorDialog.getColor(current_color, dialog, "选择颜色")
                if color.isValid():
                    btn.setStyleSheet(f"background-color: {color.name()}; border: 1px solid gray;")
                    btn.setProperty("chosen_color", color.name())
            
            btn.clicked.connect(pick_color)
            btn.setProperty("chosen_color", current_color.name())
            row.addWidget(lbl)
            row.addStretch()
            row.addWidget(btn)
            return row, btn

        main_col = QColor(self.settings.value("NeighborHighlight/main_color"))
        neigh_col = QColor(self.settings.value("NeighborHighlight/neighbor_color"))
        line_col = QColor(self.settings.value("NeighborHighlight/line_color"))

        row1, btn_main = create_color_row("主小区高亮色：", main_col)
        row2, btn_neigh = create_color_row("邻区高亮色：", neigh_col)
        row3, btn_line = create_color_row("拉线颜色：", line_col)

        layout.addLayout(row1)
        layout.addLayout(row2)
        layout.addLayout(row3)
        layout.addSpacing(10)

        btn_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btn_box.accepted.connect(dialog.accept)
        btn_box.rejected.connect(dialog.reject)
        layout.addWidget(btn_box)

        if dialog.exec_() == QDialog.Accepted:
            self.settings.setValue("NeighborHighlight/main_field", combo_main_field.currentText())
            self.settings.setValue("NeighborHighlight/neigh_field", combo_neigh_field.currentText())
            self.settings.setValue("NeighborHighlight/main_color", btn_main.property("chosen_color"))
            self.settings.setValue("NeighborHighlight/neighbor_color", btn_neigh.property("chosen_color"))
            self.settings.setValue("NeighborHighlight/line_color", btn_line.property("chosen_color"))
            self.iface.messageBar().pushSuccess("成功", "参数已保存！")


class NeighborMapTool(QgsMapToolIdentify):
    def __init__(self, iface, plugin):
        super().__init__(iface.mapCanvas())
        self.iface = iface
        self.plugin = plugin
        self.canvas = iface.mapCanvas()

    def canvasReleaseEvent(self, e):
        # 左键点击
        if e.button() == Qt.LeftButton:
            self.plugin.clean_canvas()
            
            layer = self.iface.activeLayer()
            if not layer:
                return

            # 获取点击位置的所有识别结果
            results = self.identify(e.x(), e.y(), [layer])
            if not results:
                return
            
            # 【新增】对识别结果去重（防止同一要素因为复杂的几何被重复识别）
            unique_features = {}
            for res in results:
                fid = res.mFeature.id()
                if fid not in unique_features:
                    unique_features[fid] = res.mFeature
            
            features = list(unique_features.values())
            
            # 如果只有一个主小区，直接执行
            if len(features) == 1:
                self.execute_highlight(features[0], layer)
            else:
                # 【新增】如果有多个主小区重叠，弹出菜单供用户选择
                menu = QMenu(self.canvas)
                menu.setTitle("请选择要查询的主小区")
                
                main_field = self.plugin.settings.value("NeighborHighlight/main_field")
                action_map = {}
                
                for feat in features:
                    # 列表显示的名称：优先显示主小区ID字段的值，如果没有则显示 FID
                    display_name = ""
                    if main_field:
                        val = feat.attribute(main_field)
                        if val is not None:
                            display_name = f"{main_field}: {val}"
                    
                    if not display_name:
                        display_name = f"要素 ID: {feat.id()}"
                        
                    action = menu.addAction(display_name)
                    action_map[action] = feat
                
                # 在鼠标点击的全局坐标位置弹出菜单
                global_pos = self.canvas.mapToGlobal(e.pos())
                selected_action = menu.exec_(global_pos)
                
                if selected_action in action_map:
                    chosen_feature = action_map[selected_action]
                    self.execute_highlight(chosen_feature, layer)

    def execute_highlight(self, source_feature, layer):
        main_color = QColor(self.plugin.settings.value("NeighborHighlight/main_color"))
        neigh_color = QColor(self.plugin.settings.value("NeighborHighlight/neighbor_color"))
        line_color = QColor(self.plugin.settings.value("NeighborHighlight/line_color"))
        main_field = self.plugin.settings.value("NeighborHighlight/main_field")
        neigh_field = self.plugin.settings.value("NeighborHighlight/neigh_field")

        # 1. 高亮主小区
        h_source = QgsHighlight(self.canvas, source_feature, layer)
        h_source.setColor(main_color)
        h_source.setWidth(3)
        h_source.show()
        self.plugin.main_highlight = h_source

        # 2. 读取字段并匹配邻区
        NCI_str = source_feature.attribute(neigh_field)
        main_id_val = source_feature.attribute(main_field)
        
        neighbor_fids = []
        # 判断 NCI_str 是否有值且不是纯空白
        if NCI_str and str(NCI_str).strip() != "":
            NCI_list = [n.strip() for n in str(NCI_str).split("|") if n.strip()]
            for f in layer.getFeatures():
                eci_val = f.attribute(main_field)
                if eci_val is not None and str(eci_val).strip() in NCI_list:
                    neighbor_fids.append(f.id())

        if not neighbor_fids:
            msg = f"主小区 {main_id_val} 的邻区列表为空。"
            # 【修复】改用 pushMessage 并指定 Qgis.Warning 级别
            self.iface.messageBar().pushMessage("邻区查询结果提醒", msg, level=Qgis.Warning, duration=5)
            return  # 直接返回，不再执行下面的高亮邻区和画线代码

        # 3. 高亮邻区
        self.plugin.neighbor_highlights = []
        layer.select(neighbor_fids)
        for f in layer.getFeatures(neighbor_fids):
            h = QgsHighlight(self.canvas, f, layer)
            h.setColor(neigh_color)
            h.setWidth(3)
            h.show()
            self.plugin.neighbor_highlights.append(h)

        # 4. 绘制拉线
        rb = QgsRubberBand(self.canvas, QgsWkbTypes.LineGeometry)
        rb.setColor(line_color)
        rb.setWidth(2)
        source_point = source_feature.geometry().centroid().asPoint()

        for fid in neighbor_fids:
            neighbor_feat = layer.getFeature(fid)
            neighbor_point = neighbor_feat.geometry().centroid().asPoint()
            rb.addPoint(source_point)
            rb.addPoint(neighbor_point)
            rb.addPoint(source_point)

        rb.show()
        self.plugin.rubberband = rb