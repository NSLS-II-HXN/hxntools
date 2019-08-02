from __future__ import print_function
import itertools
import logging

from ophyd import (AreaDetector, CamBase, TIFFPlugin, Component as Cpt,
                   HDF5Plugin, Device, StatsPlugin, ProcessPlugin,
                   ROIPlugin, EpicsSignal, set_and_wait)
from ophyd.areadetector.plugins import PluginBase
from ophyd.areadetector import (EpicsSignalWithRBV as SignalWithRBV)
from ophyd.areadetector.filestore_mixins import (
    FileStoreTIFF, FileStoreBase,
    FileStorePluginBase as _FileStorePluginBase)

from .utils import (makedirs, make_filename_add_subdirectory)
from ..path_signal import EpicsPathSignal, set_and_wait_path
from .trigger_mixins import (HxnModalTrigger, FileStoreBulkReadable)

from pathlib import PurePath

logger = logging.getLogger(__name__)


class DexelaTiffPlugin(TIFFPlugin, FileStoreBulkReadable, FileStoreTIFF,
                       Device):
    def mode_external(self):
        total_points = self.parent.mode_settings.total_points.get()
        self.stage_sigs[self.num_capture] = total_points

    def get_frames_per_point(self):
        mode = self.parent.mode_settings.mode.get()
        if mode == 'external':
            return 1
        else:
            return self.parent.cam.num_images.get()


class DexelaDetectorCam(CamBase):
    acquire_gain = Cpt(EpicsSignal, 'DEXAcquireGain')
    acquire_offset = Cpt(EpicsSignal, 'DEXAcquireOffset')
    binning_mode = Cpt(SignalWithRBV, 'DEXBinningMode')
    corrections_dir = Cpt(EpicsSignal, 'DEXCorrectionsDir', string=True)
    current_gain_frame = Cpt(EpicsSignal, 'DEXCurrentGainFrame')
    current_offset_frame = Cpt(EpicsSignal, 'DEXCurrentOffsetFrame')
    defect_map_available = Cpt(EpicsSignal, 'DEXDefectMapAvailable')
    defect_map_file = Cpt(EpicsSignal, 'DEXDefectMapFile', string=True)
    full_well_mode = Cpt(SignalWithRBV, 'DEXFullWellMode')
    gain_available = Cpt(EpicsSignal, 'DEXGainAvailable')
    gain_file = Cpt(EpicsSignal, 'DEXGainFile', string=True)
    load_defect_map_file = Cpt(EpicsSignal, 'DEXLoadDefectMapFile')
    load_gain_file = Cpt(EpicsSignal, 'DEXLoadGainFile')
    load_offset_file = Cpt(EpicsSignal, 'DEXLoadOffsetFile')
    num_gain_frames = Cpt(EpicsSignal, 'DEXNumGainFrames')
    num_offset_frames = Cpt(EpicsSignal, 'DEXNumOffsetFrames')
    offset_available = Cpt(EpicsSignal, 'DEXOffsetAvailable')
    offset_constant = Cpt(SignalWithRBV, 'DEXOffsetConstant')
    offset_file = Cpt(EpicsSignal, 'DEXOffsetFile', string=True)
    save_gain_file = Cpt(EpicsSignal, 'DEXSaveGainFile')
    save_offset_file = Cpt(EpicsSignal, 'DEXSaveOffsetFile')
    serial_number = Cpt(EpicsSignal, 'DEXSerialNumber')
    software_trigger = Cpt(EpicsSignal, 'DEXSoftwareTrigger')
    use_defect_map = Cpt(EpicsSignal, 'DEXUseDefectMap')
    use_gain = Cpt(EpicsSignal, 'DEXUseGain')
    use_offset = Cpt(EpicsSignal, 'DEXUseOffset')


class DexelaDetector(AreaDetector):
    cam = Cpt(DexelaDetectorCam, 'cam1:',
              read_attrs=[],
              configuration_attrs=['image_mode', 'trigger_mode',
                                   'acquire_time', 'acquire_period'],
              )


class FileStorePluginBase(_FileStorePluginBase):
    'Temporary class: if/when EpicsPathSignal is merged, this can be removed'

    def stage(self):
        # Make a filename.
        filename, read_path, write_path = self.make_filename()

        # Ensure we do not have an old file open.
        if self.file_write_mode != 'Single':
            set_and_wait(self.capture, 0)
        # These must be set before parent is staged (specifically
        # before capture mode is turned on. They will not be reset
        # on 'unstage' anyway.
        # ** NOTE ** differences here
        set_and_wait_path(self.file_path, write_path,
                          path_semantics=self.file_path.path_semantics)
        set_and_wait(self.file_name, filename)
        set_and_wait(self.file_number, 0)
        FileStoreBulkReadable.stage(self)  # skip _FileStorePluginBase, this is next in MRO
        # self._point_counter = itertools.count()
        # ** NOTE ** only difference

        # AD does this same templating in C, but we can't access it
        # so we do it redundantly here in Python.
        self._fn = self.file_template.get() % (read_path,
                                               filename,
                                               self.file_number.get() - 1)
                                               # file_number is *next* iteration
        self._fp = read_path
        if not self.file_path_exists.get():
            raise IOError("Path %s does not exist on IOC."
                          "" % self.file_path.get())


class DexelaFileStoreHDF5(FileStorePluginBase, FileStoreBulkReadable):
    _spec = 'TPX_HDF5'
    filestore_spec = _spec

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.stage_sigs.update([(self.file_template, '%s%s_%6.6d.h5'),
                                (self.file_write_mode, 'Stream'),
                                (self.compression, 'zlib'),
                                (self.capture, 1)
                                ])

    def stage(self):
        staged = super().stage()
        res_kwargs = {'frame_per_point': 1}
        logger.debug("Inserting resource with filename %s", self._fn)
        self._generate_resource(res_kwargs)

        return staged

    def make_filename(self):
        fn, read_path, write_path = super().make_filename()
        mode_settings = self.parent.mode_settings
        if mode_settings.make_directories.get():
            makedirs(read_path)
        return fn, read_path, write_path


class HDF5PluginWithFileStore(HDF5Plugin, DexelaFileStoreHDF5):
    file_path = Cpt(EpicsPathSignal, 'FilePath', path_semantics='nt',
                    kind='config')

    def stage(self):
        mode_settings = self.parent.mode_settings
        total_points = mode_settings.total_points.get()
        self.stage_sigs[self.num_capture] = total_points

        # ensure that setting capture is the last thing that's done
        self.stage_sigs.move_to_end(self.capture)
        return super().stage()


class TransformPluginV2(PluginBase):
    '''TODO/NOTE: transform plugin from R2-4 wipes away all old records

    https://github.com/areaDetector/ADCore/commit/b39ddac4a4a8d14997b94052e45ce47d72ec3ae8
    '''
    _default_suffix = 'Trans1:'
    _suffix_re = 'Trans\d:'
    _html_docs = ['NDPluginTransform.html']
    _plugin_type = 'NDPluginTransform'

    type_ = Cpt(EpicsSignal, 'Type')


class HxnDexelaDetector(HxnModalTrigger, DexelaDetector):
    hdf5 = Cpt(HDF5PluginWithFileStore, 'HDF1:',
               read_attrs=[],
               configuration_attrs=[],
               write_path_template='Z:\\%Y\\%m\\%d\\',
               read_path_template='/data/%Y/%m/%d/',
               root='/data')

    # tiff1 = Cpt(DexelaTiffPlugin, 'TIFF1:',
    #             read_attrs=[],
    #             configuration_attrs=[],
    #             write_path_template='Z:\\%Y\\%m\\%d\\',
    #             read_path_template='/data/%Y/%m/%d/')

    proc1 = Cpt(ProcessPlugin, 'Proc1:')
    stats1 = Cpt(StatsPlugin, 'Stats1:')
    stats2 = Cpt(StatsPlugin, 'Stats2:')
    stats3 = Cpt(StatsPlugin, 'Stats3:')
    stats4 = Cpt(StatsPlugin, 'Stats4:')
    stats5 = Cpt(StatsPlugin, 'Stats5:')
    transform1 = Cpt(TransformPluginV2, 'Trans1:')
    roi1 = Cpt(ROIPlugin, 'ROI1:')
    roi2 = Cpt(ROIPlugin, 'ROI2:')
    roi3 = Cpt(ROIPlugin, 'ROI3:')
    roi4 = Cpt(ROIPlugin, 'ROI4:')

    def __init__(self, prefix, *, read_attrs=None, configuration_attrs=None,
                 **kwargs):
        if read_attrs is None:
            read_attrs = ['hdf5', 'cam']
        if configuration_attrs is None:
            configuration_attrs = ['hdf5', 'cam']

        if 'hdf5' not in read_attrs:
            # ensure that hdf5 is still added, or data acquisition will fail
            read_attrs = list(read_attrs) + ['hdf5']

        super().__init__(prefix, configuration_attrs=configuration_attrs,
                         read_attrs=read_attrs, **kwargs)

    def mode_internal(self):
        super().mode_internal()

        count_time = self.count_time.get()
        if count_time is not None:
            self.stage_sigs[self.cam.acquire_time] = count_time
            self.stage_sigs[self.cam.acquire_period] = count_time + 0.005

        self.cam.stage_sigs[self.cam.trigger_mode] = 'Int. Fixed Rate'

    def mode_external(self):
        super().mode_external()

        # NOTE: read-out time without binning is significantly higher than
        #       other detectors will drop frames unless dead_time is set
        #       properly on fly-scans. Consider eventually, however complicated
        #       it may be, to use the busy signals from the detectors that
        #       support it
        self.stage_sigs[self.cam.acquire_time] = 0.005
        self.stage_sigs[self.cam.acquire_period] = 0.060

        self.cam.stage_sigs[self.cam.trigger_mode] = 'Ext. Bulb'
