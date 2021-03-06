#
# Copyright 2018 the original author or authors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

import arrow
from pyvoltha.adapters.extensions.alarms.adapter_alarms import AdapterAlarms
from pyvoltha.adapters.extensions.alarms.simulator.simulate_alarms import AdapterAlarmSimulator
from pyvoltha.adapters.extensions.alarms.olt.olt_los_alarm import OltLosAlarm
from pyvoltha.adapters.extensions.alarms.onu.onu_dying_gasp_alarm import OnuDyingGaspAlarm
from pyvoltha.adapters.extensions.alarms.onu.onu_los_alarm import OnuLosAlarm
from pyvoltha.adapters.extensions.alarms.onu.onu_lopc_miss_alarm import OnuLopcMissAlarm
from pyvoltha.adapters.extensions.alarms.onu.onu_lopc_mic_error_alarm import OnuLopcMicErrorAlarm
from pyvoltha.adapters.extensions.alarms.onu.onu_lob_alarm import OnuLobAlarm

from pyvoltha.adapters.extensions.alarms.onu.onu_startup_alarm import OnuStartupAlarm
from pyvoltha.adapters.extensions.alarms.onu.onu_signal_degrade_alarm import OnuSignalDegradeAlarm
from pyvoltha.adapters.extensions.alarms.onu.onu_signal_fail_alarm import OnuSignalFailAlarm
from pyvoltha.adapters.extensions.alarms.onu.onu_window_drift_alarm import OnuWindowDriftAlarm
from pyvoltha.adapters.extensions.alarms.onu.onu_activation_fail_alarm import OnuActivationFailAlarm

import voltha_protos.openolt_pb2 as openolt_pb2
import voltha_protos.device_pb2 as device_pb2


class OpenOltAlarmMgr(object):
    def __init__(self, log, adapter_agent, device_id, logical_device_id,
                 platform, serial_number):
        """
        20180711 -  Addition of adapter_agent and device_id
            to facilitate alarm processing and kafka posting
        :param log:
        :param adapter_agent:
        :param device_id:
        """
        self.log = log
        self.adapter_agent = adapter_agent
        self.device_id = device_id
        self.logical_device_id = logical_device_id
        self.platform = platform
        self.serial_number = serial_number
        """
        The following is added to reduce the continual posting of OLT LOS alarming
        to Kafka.   Set enable_alarm_suppress = true to enable  otherwise the
        current openolt bal will send continuous olt los alarm cleared messages
        ONU disc raised counter is place holder for a future addition
        """
        self.enable_alarm_suppress = True
        self.alarm_suppress = {"olt_los_clear": 0, "onu_disc_raised": []}  # Keep count of alarms to limit.
        try:
            self.alarms = AdapterAlarms(self.adapter_agent, self.device_id, self.logical_device_id, self.serial_number)
            self.simulator = AdapterAlarmSimulator(self.alarms)
        except Exception as initerr:
            self.log.exception("alarmhandler-init-error", errmsg=initerr.message)
            raise Exception(initerr)

    def process_alarms(self, alarm_ind):
        try:
            self.log.debug('alarm-indication', alarm=alarm_ind, device_id=self.device_id)
            if alarm_ind.HasField('los_ind'):
                self.los_indication(alarm_ind.los_ind)
            elif alarm_ind.HasField('dying_gasp_ind'):
                self.dying_gasp_indication(alarm_ind.dying_gasp_ind)
            elif alarm_ind.HasField('onu_alarm_ind'):
                self.onu_alarm_indication(alarm_ind.onu_alarm_ind)
            elif alarm_ind.HasField('onu_startup_fail_ind'):
                self.onu_startup_failure_indication(
                    alarm_ind.onu_startup_fail_ind)
            elif alarm_ind.HasField('onu_signal_degrade_ind'):
                self.onu_signal_degrade_indication(
                    alarm_ind.onu_signal_degrade_ind)
            elif alarm_ind.HasField('onu_drift_of_window_ind'):
                self.onu_drift_of_window_indication(
                    alarm_ind.onu_drift_of_window_ind)
            elif alarm_ind.HasField('onu_loss_omci_ind'):
                self.onu_loss_omci_indication(alarm_ind.onu_loss_omci_ind)
            elif alarm_ind.HasField('onu_signals_fail_ind'):
                self.onu_signals_failure_indication(
                    alarm_ind.onu_signals_fail_ind)
            elif alarm_ind.HasField('onu_tiwi_ind'):
                self.onu_transmission_interference_warning(
                    alarm_ind.onu_tiwi_ind)
            elif alarm_ind.HasField('onu_activation_fail_ind'):
                self.onu_activation_failure_indication(
                    alarm_ind.onu_activation_fail_ind)
            elif alarm_ind.HasField('onu_processing_error_ind'):
                self.onu_processing_error_indication(
                    alarm_ind.onu_processing_error_ind)
            else:
                self.log.warn('unknown alarm type', alarm=alarm_ind)

        except Exception as e:
            self.log.error('sorting of alarm went wrong', error=e,
                           alarm=alarm_ind)

    def simulate_alarm(self, alarm):
        self.simulator.simulate_alarm(alarm)

    def los_indication(self, los_ind):

        try:
            self.log.debug('los indication received', los_ind=los_ind,
                           int_id=los_ind.intf_id, status=los_ind.status)
            try:
                port_type_name = self.platform.intf_id_to_port_type_name(los_ind.intf_id)
                if los_ind.status == 1 or los_ind.status == "on":
                    # Zero out the suppression counter on OLT_LOS raise
                    self.alarm_suppress['olt_los_clear'] = 0
                    OltLosAlarm(self.alarms, intf_id=los_ind.intf_id, port_type_name=port_type_name).raise_alarm()
                else:
                    """
                        Check if there has been more that one los clear following a previous los
                    """
                    if self.alarm_suppress['olt_los_clear'] == 0 and self.enable_alarm_suppress:
                        OltLosAlarm(self.alarms, intf_id=los_ind.intf_id, port_type_name=port_type_name).clear_alarm()
                        self.alarm_suppress['olt_los_clear'] += 1

            except Exception as alarm_err:
                self.log.error('los-indication', errmsg=alarm_err.message)
        except Exception as e:
            self.log.error('los-indication', errmsg=e.message)

    def dying_gasp_indication(self, dying_gasp_ind):
        try:
            alarm_dgi = dying_gasp_ind
            onu_id = alarm_dgi.onu_id
            self.log.debug('openolt-alarmindication-dispatch-dying-gasp', int_id=alarm_dgi.intf_id,
                           onu_id=alarm_dgi.onu_id, status=alarm_dgi.status)
            try:
                """
                Get the specific onu device information for the onu generating the alarm.
                Extract the id.
                """
                onu_device_id = "unresolved"
                onu_serial_number = "unresolved"
                onu_device = self.resolve_onu_id(onu_id, port_intf_id=alarm_dgi.intf_id)
                if onu_device != None:
                    onu_device_id = onu_device.id
                    onu_serial_number = onu_device.serial_number

                if dying_gasp_ind.status == 1 or dying_gasp_ind.status == "on":
                    OnuDyingGaspAlarm(self.alarms, dying_gasp_ind.intf_id,
                                      onu_device_id, serial_number=onu_serial_number).raise_alarm()
                else:
                    OnuDyingGaspAlarm(self.alarms, dying_gasp_ind.intf_id,
                                      onu_device_id, serial_number=onu_serial_number).clear_alarm()
            except Exception as alarm_err:
                self.log.exception('dying-gasp-indication', errmsg=alarm_err.message)

        except Exception as e:
            self.log.error('dying_gasp_indication', error=e)

    def onu_alarm_indication(self, onu_alarm_ind):
        """
        LOB = Los of burst
        LOPC = Loss of PLOAM miss channel

        :param onu_alarm_ind:  Alarm indication which currently contains
            onu_id:
            los_status:
            lob_status:
            lopc_miss_status:
            lopc_mic_error_status:
        :return:
        """
        self.log.info('onu-alarm-indication')

        try:
            self.log.debug('onu alarm indication received', los_status=onu_alarm_ind.los_status,
                           onu_intf_id=onu_alarm_ind.onu_id,
                           lob_status=onu_alarm_ind.lob_status,
                           lopc_miss_status=onu_alarm_ind.lopc_miss_status,
                           lopc_mic_error_status=onu_alarm_ind.lopc_mic_error_status,
                           intf_id=onu_alarm_ind.intf_id
                           )

            try:
                """
                    Get the specific onu device information for the onu generating the alarm.
                    Extract the id.
                """
                onu_device_id = "unresolved"
                serial_number = "unresolved"
                onu_device = self.resolve_onu_id(onu_alarm_ind.onu_id,  port_intf_id=onu_alarm_ind.intf_id)
                if onu_device != None:
                    onu_device_id = onu_device.id
                    serial_number = onu_device.serial_number

                if onu_alarm_ind.los_status == 1 or onu_alarm_ind.los_status == "on":
                    OnuLosAlarm(self.alarms, onu_id=onu_device_id, intf_id=onu_alarm_ind.intf_id, serial_number=serial_number).raise_alarm()
                elif onu_alarm_ind.los_status == 0 or onu_alarm_ind.los_status == "off":
                    OnuLosAlarm(self.alarms, onu_id=onu_device_id, intf_id=onu_alarm_ind.intf_id, serial_number=serial_number).clear_alarm()
                else:     # No Change
                    pass

                if onu_alarm_ind.lopc_miss_status == 1 or onu_alarm_ind.lopc_miss_status == "on":
                    OnuLopcMissAlarm(self.alarms, onu_id=onu_device_id, intf_id=onu_alarm_ind.intf_id, serial_number=serial_number).raise_alarm()
                elif (onu_alarm_ind.lopc_miss_status == 0 or onu_alarm_ind.lopc_miss_status == "off"):
                    OnuLopcMissAlarm(self.alarms, onu_id=onu_device_id, intf_id=onu_alarm_ind.intf_id, serial_number=serial_number).clear_alarm()
                else:     # No Change
                    pass

                if onu_alarm_ind.lopc_mic_error_status == 1 or onu_alarm_ind.lopc_mic_error_status == "on":
                    OnuLopcMicErrorAlarm(self.alarms, onu_id=onu_device_id, intf_id=onu_alarm_ind.intf_id, serial_number=serial_number).raise_alarm()
                elif onu_alarm_ind.lopc_mic_error_status == 0 or onu_alarm_ind.lopc_mic_error_status == "off":
                    OnuLopcMicErrorAlarm(self.alarms, onu_id=onu_device_id, intf_id=onu_alarm_ind.intf_id, serial_number=serial_number).clear_alarm()
                else:     # No Change
                    pass

                if onu_alarm_ind.lob_status == 1 or onu_alarm_ind.lob_status == "on":
                    OnuLobAlarm(self.alarms, onu_id=onu_device_id, intf_id=onu_alarm_ind.intf_id, serial_number=serial_number).raise_alarm()
                elif onu_alarm_ind.lob_status == 0 or onu_alarm_ind.lob_status == "off":
                    OnuLobAlarm(self.alarms, onu_id=onu_device_id, intf_id=onu_alarm_ind.intf_id, serial_number=serial_number).clear_alarm()
                else:     # No Change
                    pass
            except Exception as alarm_err:
                self.log.exception('onu-alarm-indication', errmsg=alarm_err.message)

        except Exception as e:
            self.log.exception('onu-alarm-indication', errmsg=e.message)

    def onu_startup_failure_indication(self, onu_startup_fail_ind):
        """
        Current protobuf indicator:
        message OnuStartupFailureIndication {
                fixed32 intf_id = 1;
                fixed32 onu_id = 2;
                string status = 3;
            }

        :param onu_startup_fail_ind:
        :return:
        """
        try:
            ind = onu_startup_fail_ind
            label = "onu-startup-failure-indication"
            self.log.debug(label + " received", onu_startup_fail_ind=ind, int_id=ind.intf_id, onu_id=ind.onu_id, status=ind.status)
            try:
                """
                    Get the specific onu device information for the onu generating the alarm.
                """
                serial_number = "unresolved"
                onu_device = self.resolve_onu_id(ind.onu_id,  port_intf_id=ind.intf_id)
                if onu_device != None:
                    serial_number = onu_device.serial_number
                    
                if ind.status == 1 or ind.status == "on":
                    OnuStartupAlarm(self.alarms, intf_id=ind.intf_id,onu_id=ind.onu_id, serial_number=serial_number).raise_alarm()
                else:
                    OnuStartupAlarm(self.alarms, intf_id=ind.intf_id, onu_id=ind.onu_id, serial_number=serial_number).clear_alarm()
            except Exception as alarm_err:
                self.log.exception(label, errmsg=alarm_err.message)

        except Exception as e:
            self.log.exception(label, errmsg=e.message)

    def onu_signal_degrade_indication(self, onu_signal_degrade_ind):
        """
        Current protobuf indicator:
        OnuSignalDegradeIndication {
            fixed32 intf_id = 1;
            fixed32 onu_id = 2;
            string status = 3;
            fixed32 inverse_bit_error_rate = 4;
        }
        :param onu_signal_degrade_ind:
        :return:
        """
        try:
            ind = onu_signal_degrade_ind
            label = "onu-signal-degrade-indication"
            self.log.debug(label + ' received',
                           onu_startup_fail_ind=ind,
                           int_id=ind.intf_id,
                           onu_id=ind.onu_id,
                           inverse_bit_error_rate=ind.inverse_bit_error_rate,
                           status=ind.status)
            try:
                """
                    Get the specific onu device information for the onu generating the alarm.
                    Extract the id.   In the future extract the serial number as well
                """
                serial_number = "unresolved"
                onu_device = self.resolve_onu_id(ind.onu_id,  port_intf_id=ind.intf_id)
                if onu_device != None:
                    serial_number = onu_device.serial_number

                if ind.status == 1 or ind.status == "on":
                    OnuSignalDegradeAlarm(self.alarms, intf_id=ind.intf_id, onu_id=ind.onu_id,
                                          inverse_bit_error_rate=ind.inverse_bit_error_rate, serial_number=serial_number).raise_alarm()
                else:
                    OnuSignalDegradeAlarm(self.alarms, intf_id=ind.intf_id, onu_id=ind.onu_id,
                                          inverse_bit_error_rate=ind.inverse_bit_error_rate, serial_number=serial_number).clear_alarm()
            except Exception as alarm_err:
                self.log.exception(label, errmsg=alarm_err.message)

        except Exception as e:
            self.log.exception(label, errmsg=e.message)

    def onu_drift_of_window_indication(self, onu_drift_of_window_ind):
        """
        Current protobuf indicator:
        OnuDriftOfWindowIndication {
            fixed32 intf_id = 1;
            fixed32 onu_id = 2;
            string status = 3;
            fixed32 drift = 4;
            fixed32 new_eqd = 5;
        }

        :param onu_drift_of_window_ind:
        :return:
        """
        try:
            ind = onu_drift_of_window_ind
            label = "onu-window-drift-indication"

            onu_device_id, onu_serial_number = self.resolve_onudev_id_onudev_serialnum(
                self.resolve_onu_id(ind.onu_id, port_intf_id=ind.intf_id))

            self.log.debug(label + ' received',
                           onu_drift_of_window_ind=ind,
                           int_id=ind.intf_id,
                           onu_id=ind.onu_id,
                           onu_device_id=onu_device_id,
                           drift=ind.drift,
                           new_eqd=ind.new_eqd,
                           status=ind.status)
            try:
                if ind.status == 1 or ind.status == "on":
                    OnuWindowDriftAlarm(self.alarms, intf_id=ind.intf_id,
                           onu_id=onu_device_id,
                           drift=ind.drift,
                           new_eqd=ind.new_eqd,
                           serial_number=onu_serial_number).raise_alarm()
                else:
                    OnuWindowDriftAlarm(self.alarms, intf_id=ind.intf_id,
                           onu_id=onu_device_id,
                           drift=ind.drift,
                           new_eqd=ind.new_eqd,
                           serial_number=onu_serial_number).clear_alarm()
            except Exception as alarm_err:
                self.log.exception(label, errmsg=alarm_err.message)

        except Exception as e:
            self.log.exception(label, errmsg=e.message)

    def onu_loss_omci_indication(self, onu_loss_omci_ind):
        self.log.info('not implemented yet')

    def onu_signals_failure_indication(self, onu_signals_fail_ind):
        """
        Current protobuf indicator:
        OnuSignalsFailureIndication {
            fixed32 intf_id = 1;
            fixed32 onu_id = 2;
            string status = 3;
            fixed32 inverse_bit_error_rate = 4;
        }

        :param onu_signals_fail_ind:
        :return:
        """
        try:
            ind = onu_signals_fail_ind
            label = "onu-signal-failure-indication"

            onu_device_id, onu_serial_number = self.resolve_onudev_id_onudev_serialnum(
                self.resolve_onu_id(ind.onu_id, port_intf_id=ind.intf_id))

            self.log.debug(label + ' received',
                           onu_startup_fail_ind=ind,
                           int_id=ind.intf_id,
                           onu_id=ind.onu_id,
                           onu_device_id=onu_device_id,
                           onu_serial_number=onu_serial_number,
                           inverse_bit_error_rate=ind.inverse_bit_error_rate,
                           status=ind.status)
            try:
                if ind.status == 1 or ind.status == "on":
                    OnuSignalFailAlarm(self.alarms, intf_id=ind.intf_id,
                           onu_id=onu_device_id,
                           inverse_bit_error_rate=ind.inverse_bit_error_rate,
                           serial_number=onu_serial_number).raise_alarm()
                else:
                    OnuSignalFailAlarm(self.alarms, intf_id=ind.intf_id,
                           onu_id=onu_device_id,
                           inverse_bit_error_rate=ind.inverse_bit_error_rate,
                           serial_number=onu_serial_number).clear_alarm()
            except Exception as alarm_err:
                self.log.exception(label, errmsg=alarm_err.message)

        except Exception as e:
            self.log.exception(label, errmsg=e.message)


    def onu_transmission_interference_warning(self, onu_tiwi_ind):
        self.log.info('not implemented yet')

    def onu_activation_failure_indication(self, onu_activation_fail_ind):
        """

        No status is currently passed with this alarm. Consequently it will always just raise
        :param onu_activation_fail_ind:
        :return:
        """
        try:
            ind = onu_activation_fail_ind
            label = "onu-activation-failure-indication"

            onu_device_id, onu_serial_number = self.resolve_onudev_id_onudev_serialnum(
                self.resolve_onu_id(ind.onu_id, port_intf_id=ind.intf_id))

            self.log.debug(label + ' received',
                           onu_startup_fail_ind=ind,
                           int_id=ind.intf_id,
                           onu_id=ind.onu_id,
                           onu_device_id=onu_device_id,
                           onu_serial_number=onu_serial_number)
            try:

                OnuActivationFailAlarm(self.alarms, intf_id=ind.intf_id,
                       onu_id=onu_device_id, serial_number=onu_serial_number).raise_alarm()
            except Exception as alarm_err:
                self.log.exception(label, errmsg=alarm_err.message)

        except Exception as e:
            self.log.exception(label, errmsg=e.message)

    def onu_processing_error_indication(self, onu_processing_error_ind):
        self.log.info('not implemented yet')

    """
    Helper Methods
    """

    def resolve_onudev_id_onudev_serialnum(self,onu_device):
        """
        Convenience wrapper to resolve device_id and serial number
        :param onu_device:
        :return: tuple: onu_device_id, onu_serial_number
        """
        try:
            onu_device_id = "unresolved"
            onu_serial_number = "unresolved"
            if onu_device != None:
                onu_device_id = onu_device.id
                onu_serial_number = onu_device.serial_number
        except Exception as err:
            self.log.exception("openolt-alarms-resolve-onudev-id  ", errmsg=err.message)
            raise Exception(err)
        return onu_device_id, onu_serial_number

    def resolve_onu_id(self, onu_id, port_intf_id):
        """
        Resolve the onu_device from the intf_id value and port. Uses the adapter agent to
        resolve this..

        Returns None if not found. Caller will have to test for None and act accordingly.
        :param onu_id:
        :param port_intf_id:
        :return:
        """

        try:
            onu_device = None
            onu_device = self.adapter_agent.get_child_device(
                self.device_id,
                parent_port_no=self.platform.intf_id_to_port_no(
                    port_intf_id, device_pb2.Port.PON_OLT),
                onu_id=onu_id)
        except Exception as inner:
            self.log.exception('resolve-onu-id', errmsg=inner.message)

        return onu_device

