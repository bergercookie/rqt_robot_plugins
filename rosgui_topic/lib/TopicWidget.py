#!/usr/bin/env python
# -*- coding: utf-8 -*-
import os

from rosgui.QtBindingHelper import import_from_qt, loadUi
Qt, QTimer, Slot = import_from_qt(['Qt', 'QTimer', 'Slot'], 'QtCore')
QDockWidget, QTreeWidgetItem, QMenu = import_from_qt(['QDockWidget', 'QTreeWidgetItem', 'QMenu'], 'QtGui')

import roslib
roslib.load_manifest('rosgui_topic')
import rospy
import TopicInfo
reload(TopicInfo) # force reload to update on changes during runtime


# main class inherits from the ui window class
class TopicWidget(QDockWidget):
    column_names_ = ['topic', 'type', 'bandwidth', 'rate', 'value']

    def __init__(self, plugin, plugin_context):
        QDockWidget.__init__(self, plugin_context.main_window())
        ui_file = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'TopicWidget.ui')
        loadUi(ui_file, self)
        self.plugin_ = plugin

        self.current_topic_list_ = []
        self.topic_infos_ = {}
        self.tree_items_ = {}
        self.column_index_ = {}
        for column_name in self.column_names_:
            self.column_index_[column_name] = len(self.column_index_)

        self.refresh_topics()
        # init and start update timer
        self.timer_update_ = QTimer(self)
        self.timer_update_.timeout.connect(self.refresh_topics)
        self.timer_update_.start(1000)


    @Slot()
    def refresh_topics(self):
        # fill tree view
        topic_list = rospy.get_published_topics()
        if self.current_topic_list_ != topic_list:
            self.current_topic_list_ = topic_list

            # start new topic dict
            self.topics_tree_widget.clear()
            new_topic_infos = {}

            for topic_name, message_type in topic_list:
                # if topic is new
                if not self.topic_infos_.has_key(topic_name):
                    # create new Topicinfo
                    topic_info = TopicInfo.TopicInfo(topic_name)
                    # if successful add it to the dict
                    if topic_info.topic_name_:
                        new_topic_infos[topic_name] = topic_info
                else:
                    # if topic has been seen before, copy it to new dict and remove it form the old one
                    new_topic_infos[topic_name] = self.topic_infos_[topic_name]
                    del self.topic_infos_[topic_name]

                # if TopicInfo exist for topic, add it to tree view
                if topic_name in new_topic_infos:
                    self._recursive_create_widget_items(self.topics_tree_widget, topic_name, message_type, new_topic_infos[topic_name].message_class_)

            # stop monitoring and delete non existing topics
            for topic_info in self.topic_infos_.values():
                topic_info.stop_monitoring()
                del topic_info

            # change to new topic dict
            self.topic_infos_ = new_topic_infos


        for topic_info in self.topic_infos_.values():
            if topic_info.monitoring_:
                # update rate
                rate, _, _, _ = topic_info.get_hz()
                rate_text = '%1.2f' % rate if rate != None else 'unknown'

                # update bandwidth
                bytes_per_s, _, _, _ = topic_info.get_bw()
                if bytes_per_s == None:
                    bandwidth_text = 'unknown'
                elif bytes_per_s < 1000:
                    bandwidth_text = '%.2fB/s' % bytes_per_s
                elif bytes_per_s < 1000000:
                    bandwidth_text = '%.2fKB/s' % (bytes_per_s / 1000.)
                else:
                    bandwidth_text = '%.2fMB/s' % (bytes_per_s / 1000000.)

                # update values
                value_text = ''
                self.update_value(topic_info.topic_name_, topic_info.last_message_)

            else:
                rate_text = ''
                bandwidth_text = ''
                value_text = 'not monitored'

            self.tree_items_[topic_info.topic_name_].setText(self.column_index_['rate'], rate_text)
            self.tree_items_[topic_info.topic_name_].setText(self.column_index_['bandwidth'], bandwidth_text)
            self.tree_items_[topic_info.topic_name_].setText(self.column_index_['value'], value_text)


        # resize columns
        for i in range(self.topics_tree_widget.columnCount()):
            self.topics_tree_widget.resizeColumnToContents(i)

        # limit width of value column
        current_width = self.topics_tree_widget.columnWidth(self.column_index_ ['value'])
        self.topics_tree_widget.setColumnWidth(self.column_index_ ['value'], min(150, current_width))


    def update_value(self, topic_name, message):
        if hasattr(message, '__slots__'):
            for slot_name in message.__slots__:
                self.update_value(topic_name + '/' + slot_name, getattr(message, slot_name))
        else:
            if self.tree_items_.has_key(topic_name):
                self.tree_items_[topic_name].setText(self.column_index_['value'], repr(message))


    def _recursive_create_widget_items(self, parent, topic_name, type_name, message):
        if parent == self.topics_tree_widget:
            # show full topic name with preceding namespace on toplevel item
            topic_text = topic_name
        else:
            topic_text = topic_name.split('/')[-1]
        item = QTreeWidgetItem(parent)
        item.setText(self.column_index_['topic'], topic_text)
        item.setText(self.column_index_['type'], type_name)
        item.setData(0, Qt.UserRole, topic_name)
        self.tree_items_[topic_name] = item
        if hasattr(message, '__slots__') and hasattr(message, '_slot_types'):
            for slot_name, type_name in zip(message.__slots__, message._slot_types):
                self._recursive_create_widget_items(item, topic_name + '/' + slot_name, type_name, getattr(message, slot_name))


    @Slot('QPoint')
    def on_topics_tree_widget_customContextMenuRequested(self, pos):
        item = self.topics_tree_widget.itemAt(pos)
        if not item:
            return
        topic_name = item.data(0, Qt.UserRole)

        menu = QMenu(self)
        actionToggleMonitoring = menu.addAction("Toggle Monitoring")
        action = menu.exec_(self.topics_tree_widget.mapToGlobal(pos))
        if action == actionToggleMonitoring:
            self.topic_infos_[topic_name].toggle_monitoring()


    # override Qt's closeEvent() method to trigger plugin unloading
    def closeEvent(self, event):
        for topic_info in self.topic_infos_.values():
            topic_info.stop_monitoring()
        self.timer_update_.stop()
        QDockWidget.closeEvent(self, event)
        if event.isAccepted():
            self.plugin_.deleteLater()
