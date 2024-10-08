from enum import IntEnum
import logging

from ophyd import (Device, Component as Cpt, FormattedComponent as FC,
                   Signal)
from ophyd import (EpicsSignal, EpicsSignalRO, DeviceStatus)

from .trigger_mixins import HxnModalBase

logger = logging.getLogger(__name__)


def _get_configuration_attrs(inst, *, signal_class=Signal):
    cls = inst.__class__
    return [sig_name for sig_name in cls.component_names
            if issubclass(getattr(cls, sig_name).cls, signal_class)]


class ZebraInputEdge(IntEnum):
    FALLING = 1
    RISING = 0


class ZebraAddresses(IntEnum):
    DISCONNECT = 0
    IN1_TTL = 1
    IN1_NIM = 2
    IN1_LVDS = 3
    IN2_TTL = 4
    IN2_NIM = 5
    IN2_LVDS = 6
    IN3_TTL = 7
    IN3_OC = 8
    IN3_LVDS = 9
    IN4_TTL = 10
    IN4_CMP = 11
    IN4_PECL = 12
    IN5_ENCA = 13
    IN5_ENCB = 14
    IN5_ENCZ = 15
    IN5_CONN = 16
    IN6_ENCA = 17
    IN6_ENCB = 18
    IN6_ENCZ = 19
    IN6_CONN = 20
    IN7_ENCA = 21
    IN7_ENCB = 22
    IN7_ENCZ = 23
    IN7_CONN = 24
    IN8_ENCA = 25
    IN8_ENCB = 26
    IN8_ENCZ = 27
    IN8_CONN = 28
    PC_ARM = 29
    PC_GATE = 30
    PC_PULSE = 31
    AND1 = 32
    AND2 = 33
    AND3 = 34
    AND4 = 35
    OR1 = 36
    OR2 = 37
    OR3 = 38
    OR4 = 39
    GATE1 = 40
    GATE2 = 41
    GATE3 = 42
    GATE4 = 43
    DIV1_OUTD = 44
    DIV2_OUTD = 45
    DIV3_OUTD = 46
    DIV4_OUTD = 47
    DIV1_OUTN = 48
    DIV2_OUTN = 49
    DIV3_OUTN = 50
    DIV4_OUTN = 51
    PULSE1 = 52
    PULSE2 = 53
    PULSE3 = 54
    PULSE4 = 55
    QUAD_OUTA = 56
    QUAD_OUTB = 57
    CLOCK_1KHZ = 58
    CLOCK_1MHZ = 59
    SOFT_IN1 = 60
    SOFT_IN2 = 61
    SOFT_IN3 = 62
    SOFT_IN4 = 63


class EpicsSignalWithRBV(EpicsSignal):
    # An EPICS signal that uses the Zebra convention of 'pvname' being the
    # setpoint and 'pvname:RBV' being the read-back

    def __init__(self, prefix, **kwargs):
        super().__init__(prefix + ':RBV', write_pv=prefix, **kwargs)


class ZebraPulse(Device):
    width = Cpt(EpicsSignalWithRBV, 'WID')
    input_addr = Cpt(EpicsSignalWithRBV, 'INP')
    input_str = Cpt(EpicsSignalRO, 'INP:STR', string=True)
    input_status = Cpt(EpicsSignalRO, 'INP:STA')
    delay = Cpt(EpicsSignalWithRBV, 'DLY')
    delay_sync = Cpt(EpicsSignal, 'DLY:SYNC')
    time_units = Cpt(EpicsSignalWithRBV, 'PRE', string=True)
    output = Cpt(EpicsSignal, 'OUT')

    input_edge = FC(EpicsSignal,
                    '{self._zebra_prefix}POLARITY:{self._edge_addr}')

    _edge_addrs = {1: 'BC',
                   2: 'BD',
                   3: 'BE',
                   4: 'BF',
                   }

    def __init__(self, prefix, *, index=None, parent=None,
                 configuration_attrs=None, read_attrs=None, **kwargs):
        if read_attrs is None:
            read_attrs = []
        if configuration_attrs is None:
            configuration_attrs = _get_configuration_attrs(self)

        zebra = parent
        self.index = index
        self._zebra_prefix = zebra.prefix
        self._edge_addr = self._edge_addrs[index]

        super().__init__(prefix, configuration_attrs=configuration_attrs,
                         read_attrs=read_attrs, parent=parent, **kwargs)


class ZebraOutputBase(Device):
    '''The base of all zebra outputs (1~8)

        Front outputs
        # TTL  LVDS  NIM  PECL  OC  ENC
        1  o    o     o
        2  o    o     o
        3  o    o               o
        4  o          o    o

        Rear outputs
        # TTL  LVDS  NIM  PECL  OC  ENC
        5                            o
        6                            o
        7                            o
        8                            o

    '''
    def __init__(self, prefix, *, index=None, read_attrs=None,
                 configuration_attrs=None, **kwargs):
        self.index = index

        if read_attrs is None:
            read_attrs = []
        if configuration_attrs is None:
            configuration_attrs = _get_configuration_attrs(self)

        super().__init__(prefix, read_attrs=read_attrs,
                         configuration_attrs=configuration_attrs, **kwargs)


class ZebraOutputType(Device):
    '''Shared by all output types (ttl, lvds, nim, pecl, out)'''
    addr = Cpt(EpicsSignalWithRBV, '')
    status = Cpt(EpicsSignalRO, ':STA')
    string = Cpt(EpicsSignalRO, ':STR', string=True)
    sync = Cpt(EpicsSignal, ':SYNC')
    write_output = Cpt(EpicsSignal, ':SET')

    def __init__(self, prefix, *, read_attrs=None, configuration_attrs=None,
                 **kwargs):
        if read_attrs is None:
            read_attrs = []
        if configuration_attrs is None:
            configuration_attrs = _get_configuration_attrs(self)

        super().__init__(prefix, read_attrs=read_attrs,
                         configuration_attrs=configuration_attrs, **kwargs)


class ZebraFrontOutput12(ZebraOutputBase):
    ttl = Cpt(ZebraOutputType, 'TTL')
    lvds = Cpt(ZebraOutputType, 'LVDS')
    nim = Cpt(ZebraOutputType, 'NIM')


class ZebraFrontOutput3(ZebraOutputBase):
    ttl = Cpt(ZebraOutputType, 'TTL')
    lvds = Cpt(ZebraOutputType, 'LVDS')
    open_collector = Cpt(ZebraOutputType, 'OC')


class ZebraFrontOutput4(ZebraOutputBase):
    ttl = Cpt(ZebraOutputType, 'TTL')
    nim = Cpt(ZebraOutputType, 'NIM')
    pecl = Cpt(ZebraOutputType, 'PECL')


class ZebraRearOutput(ZebraOutputBase):
    enca = Cpt(ZebraOutputType, 'ENCA')
    encb = Cpt(ZebraOutputType, 'ENCB')
    encz = Cpt(ZebraOutputType, 'ENCZ')
    conn = Cpt(ZebraOutputType, 'CONN')


class ZebraGateInput(Device):
    addr = Cpt(EpicsSignalWithRBV, '')
    string = Cpt(EpicsSignalRO, ':STR', string=True)
    status = Cpt(EpicsSignalRO, ':STA')
    sync = Cpt(EpicsSignal, ':SYNC')
    write_input = Cpt(EpicsSignal, ':SET')

    # Input edge index depends on the gate number (these are set in __init__)
    edge = FC(EpicsSignal,
              '{self._zebra_prefix}POLARITY:B{self._input_edge_idx}')

    def __init__(self, prefix, *, index=None, parent=None,
                 configuration_attrs=None, read_attrs=None, **kwargs):
        if read_attrs is None:
            read_attrs = []
        if configuration_attrs is None:
            configuration_attrs = _get_configuration_attrs(self)

        gate = parent
        zebra = gate.parent

        self.index = index
        self._zebra_prefix = zebra.prefix
        self._input_edge_idx = gate._input_edge_idx[self.index]

        super().__init__(prefix, read_attrs=read_attrs,
                         configuration_attrs=configuration_attrs,
                         parent=parent, **kwargs)


class ZebraGate(Device):
    input1 = Cpt(ZebraGateInput, 'INP1', index=1)
    input2 = Cpt(ZebraGateInput, 'INP2', index=2)
    output = Cpt(EpicsSignal, 'OUT')

    def __init__(self, prefix, *, index=None, read_attrs=None,
                 configuration_attrs=None, **kwargs):
        self.index = index
        self._input_edge_idx = {1: index - 1,
                                2: 4 + index - 1
                                }

        if read_attrs is None:
            read_attrs = []
        if configuration_attrs is None:
            configuration_attrs = ['output']

        super().__init__(prefix, configuration_attrs=configuration_attrs,
                         read_attrs=read_attrs, **kwargs)

    def set_input_edges(self, edge1, edge2):
        self.input1.edge.set(int(edge1)).wait()
        self.input2.edge.set(int(edge2)).wait()


class Zebra(HxnModalBase, Device):
    soft_input1 = Cpt(EpicsSignal, 'SOFT_IN:B0')
    soft_input2 = Cpt(EpicsSignal, 'SOFT_IN:B1')
    soft_input3 = Cpt(EpicsSignal, 'SOFT_IN:B2')
    soft_input4 = Cpt(EpicsSignal, 'SOFT_IN:B3')

    pulse1 = Cpt(ZebraPulse, 'PULSE1_', index=1)
    pulse2 = Cpt(ZebraPulse, 'PULSE2_', index=2)
    pulse3 = Cpt(ZebraPulse, 'PULSE3_', index=3)
    pulse4 = Cpt(ZebraPulse, 'PULSE4_', index=4)

    output1 = Cpt(ZebraFrontOutput12, 'OUT1_', index=1)
    output2 = Cpt(ZebraFrontOutput12, 'OUT2_', index=2)
    output3 = Cpt(ZebraFrontOutput3, 'OUT3_', index=3)
    output4 = Cpt(ZebraFrontOutput4, 'OUT4_', index=4)

    output5 = Cpt(ZebraRearOutput, 'OUT5_', index=5)
    output6 = Cpt(ZebraRearOutput, 'OUT6_', index=6)
    output7 = Cpt(ZebraRearOutput, 'OUT7_', index=7)
    output8 = Cpt(ZebraRearOutput, 'OUT8_', index=8)

    gate1 = Cpt(ZebraGate, 'GATE1_', index=1)
    gate2 = Cpt(ZebraGate, 'GATE2_', index=2)
    gate3 = Cpt(ZebraGate, 'GATE3_', index=3)
    gate4 = Cpt(ZebraGate, 'GATE4_', index=4)

    addresses = ZebraAddresses

    def __init__(self, prefix, *, configuration_attrs=None, read_attrs=None,
                 **kwargs):
        if read_attrs is None:
            read_attrs = []
        if configuration_attrs is None:
            configuration_attrs = _get_configuration_attrs(self)

        super().__init__(prefix, configuration_attrs=configuration_attrs,
                         read_attrs=read_attrs, **kwargs)

        self.pulse = dict(self._get_indexed_devices(ZebraPulse))
        self.output = dict(self._get_indexed_devices(ZebraOutputBase))
        self.gate = dict(self._get_indexed_devices(ZebraGate))

    def _get_indexed_devices(self, cls):
        for attr in self._sub_devices:
            dev = getattr(self, attr)
            if isinstance(dev, cls):
                yield dev.index, dev

    def mode_internal(self):
        super().mode_internal()
        # handle the scan type here

    def mode_external(self):
        super().mode_external()
        # handle the scan type here

    def trigger(self):
        # Re-implement this to trigger as desired in bluesky
        status = DeviceStatus(self)
        status._finished()
        return status


class HxnZebra(Zebra):
    def mode_internal(self):
        super().mode_internal()

        scan_type = self.mode_settings.scan_type.get()
        # no concept of internal triggering for now
        # raise ValueError('Unknown scan type for internal triggering: '
        #                  '{}'.format(scan_type))

    def mode_external(self):
        super().mode_external()

        scan_type = self.mode_settings.scan_type.get()
        if scan_type == 'fly':
            # PMAC motion script outputs 0 during exposure
            # * Gate 1 - active low devices (low during exposure)
            self.gate[1].input1.addr.put(ZebraAddresses.IN3_OC)
            self.gate[1].input2.addr.put(ZebraAddresses.IN3_OC)
            self.gate[1].set_input_edges(ZebraInputEdge.FALLING,
                                         ZebraInputEdge.RISING)

            # Pulse 1 - modulate pulse width for Eiger trigger
            self.pulse[1].input_addr.put(ZebraAddresses.IN3_OC)
            self.pulse[1].delay.put(0)
            self.pulse[1].time_units.put('s')

            # Pulse 2 - 1ms pulse for scaler 1 gate
            self.pulse[2].input_addr.put(ZebraAddresses.IN3_OC)
            self.pulse[2].delay.put(0)
            self.pulse[2].input_edge.put(0)
            self.pulse[2].width.put(0.001)
            self.pulse[2].time_units.put('s')

            # Pulse 3 - 1ms pulse for scaler 1 inhibit
            self.pulse[3].input_addr.put(ZebraAddresses.IN3_OC)
            self.pulse[3].delay.put(0)
            self.pulse[3].input_edge.put(1)
            self.pulse[3].width.put(0.001)
            self.pulse[3].time_units.put('s')

            # Output 1 - timepix (OR merlin, see below)
            # self.output[1].ttl.addr.put(ZebraAddresses.GATE1)

            # * Gate 2 - Active high (high during exposure)
            self.gate[2].input1.addr.put(ZebraAddresses.IN3_OC)
            self.gate[2].input2.addr.put(ZebraAddresses.IN3_OC)
            self.gate[2].set_input_edges(ZebraInputEdge.RISING,
                                         ZebraInputEdge.FALLING)

            # Output 1 - merlin and dexela and eiger
            self.output[1].ttl.addr.put(ZebraAddresses.GATE2)
            #self.output[1].ttl.addr.put(ZebraAddresses.PULSE1)

            # Output 2 - scaler 1 inhibit
            self.output[2].ttl.addr.put(ZebraAddresses.GATE2)
            #self.output[2].ttl.addr.put(ZebraAddresses.DISCONNECT)
            #self.output[2].ttl.addr.put(ZebraAddresses.PULSE1)

            # Output 3 - scaler 1 gate
            self.output[3].ttl.addr.put(ZebraAddresses.GATE2)
            #self.output[3].ttl.addr.put(ZebraAddresses.PULSE1)

            # Output 4 - xspress 3
            self.output[4].ttl.addr.put(ZebraAddresses.GATE2)

            # Merlin LVDS
            # self.output[1].lvds.put(ZebraAddresses.GATE2)

        elif scan_type == 'step':
            # Scaler triggers all detectors
            # Scaler, output mode 1, LNE (output 5) connected to Zebra IN1_TTL
            # Pulse 1 has pulse width set to the count_time

            # OUT1_TTL Merlin / dexela
            # OUT2_TTL Scaler 1 inhibit
            #
            # OUT3_TTL Scaler 1 gate
            # OUT4_TTL Xspress3
            self.pulse[1].input_addr.put(ZebraAddresses.IN1_TTL)

            count_time = self.count_time.get()
            if count_time is not None:
                logger.debug('Step scan pulse-width is %s', count_time)
                self.pulse[1].width.put(count_time)
                self.pulse[1].time_units.put('s')

            self.pulse[1].delay.put(0.0)
            self.pulse[1].input_edge.put(ZebraInputEdge.FALLING)

            # To be used in regular scaler mode, scaler 1 has to have
            # inhibit cleared and counting enabled:
            self.soft_input4.put(1)

            # Timepix
            # self.output[1].ttl.addr.put(ZebraAddresses.PULSE1)
            # Merlin
            self.output[1].ttl.addr.put(ZebraAddresses.PULSE1)
            self.output[2].ttl.addr.put(ZebraAddresses.SOFT_IN4)

            self.gate[2].input1.addr.put(ZebraAddresses.PULSE1)
            self.gate[2].input2.addr.put(ZebraAddresses.PULSE1)
            self.gate[2].set_input_edges(ZebraInputEdge.RISING,
                                         ZebraInputEdge.FALLING)

            self.output[3].ttl.addr.put(ZebraAddresses.SOFT_IN4)
            self.output[4].ttl.addr.put(ZebraAddresses.GATE2)

            # Merlin LVDS
            self.output[1].lvds.addr.put(ZebraAddresses.PULSE1)
        else:
            raise ValueError('Unknown scan type for external triggering: '
                             '{}'.format(scan_type))
