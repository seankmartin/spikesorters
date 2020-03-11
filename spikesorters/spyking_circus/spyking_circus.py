import copy
from pathlib import Path
import os
import numpy as np
import sys

import spikeextractors as se
from ..basesorter import BaseSorter
from ..utils.shellscript import ShellScript

try:
    import circus
    HAVE_SC = True
except ImportError:
    HAVE_SC = False


class SpykingcircusSorter(BaseSorter):
    """
    """

    sorter_name = 'spykingcircus'
    installed = HAVE_SC
    requires_locations = False

    _default_params = {
        'detect_sign': -1,  # -1 - 1 - 0
        'adjacency_radius': 100,  # Channel neighborhood adjacency radius corresponding to geom file
        'detect_threshold': 6,  # Threshold for detection
        'template_width_ms': 3,  # Spyking circus parameter
        'filter': True,
        'merge_spikes': True,
        'auto_merge': 0.75,
        'num_workers': None,
        'whitening_max_elts': 1000,  # I believe it relates to subsampling and affects compute time
        'clustering_max_elts': 10000,  # I believe it relates to subsampling and affects compute time
        }

    _extra_gui_params = [
        {'name': 'detect_sign', 'type': 'int', 'value': -1, 'default': -1,
         'title': "Use -1, 0, or 1, depending on the sign of the spikes in the recording"},
        {'name': 'adjacency_radius', 'type': 'float', 'value': 100.0, 'default': 100.0,
         'title': "Distance (in microns) of the adjacency radius"},
        {'name': 'detect_threshold', 'type': 'float', 'value': 6.0, 'default': 6.0, 'title': "Threshold for detection"},
        {'name': 'template_width_ms', 'type': 'float', 'value': 3.0, 'default': 3.0, 'title': "Width of templates (ms)"},
        {'name': 'filter', 'type': 'bool', 'value': True, 'default': True,
         'title': "If True, the recording will be filtered"},
        {'name': 'merge_spikes', 'type': 'bool', 'value': True, 'default': True,
         'title': "If True, spikes will be merged at the end."},
        {'name': 'auto_merge', 'type': 'float', 'value': 0.75, 'default': 0.75, 'title': "Auto-merge value"},
        {'name': 'num_workers', 'type': 'int', 'value': None, 'default': None, 'title': "Number of parallel workers"},
        {'name': 'whitening_max_elts', 'type': 'int', 'value': 1000, 'default': 1000, 'title': "Related to subsampling"},
        {'name': 'clustering_max_elts', 'type': 'int', 'value': 10000, 'default': 10000, 'title': "Related to subsampling"},
    ]

    sorter_gui_params = copy.deepcopy(BaseSorter.sorter_gui_params)
    for param in _extra_gui_params:
        sorter_gui_params.append(param)

    installation_mesg = """
        >>> pip install spyking-circus

        Need MPICH working, for ubuntu do:
            sudo apt install libmpich-dev mpich

        More information on Spyking-Circus at:
            https://spyking-circus.readthedocs.io/en/latest/
    """

    def __init__(self, **kargs):
        BaseSorter.__init__(self, **kargs)

    @staticmethod
    def get_sorter_version():
        return circus.__version__

    def _setup_recording(self, recording, output_folder):
        p = self.params
        source_dir = Path(__file__).parent

        # save prb file
        # note: only one group here, the split is done in basesorter
        probe_file = output_folder / 'probe.prb'
        recording.save_to_probe_file(probe_file, grouping_property=None,
                                     radius=p['adjacency_radius'])

        # save binary file
        file_name = 'recording'
        # n_chan = recording.get_num_channels()

        if p['detect_sign'] < 0:
            detect_sign = 'negative'
        elif p['detect_sign'] > 0:
            detect_sign = 'positive'
        else:
            detect_sign = 'both'

        sample_rate = float(recording.get_sampling_frequency())

        # set up spykingcircus config file
        with (source_dir / 'config_default.params').open('r') as f:
            circus_config = f.readlines()
        if p['merge_spikes']:
            auto = p['auto_merge']
        else:
            auto = 0
        circus_config = ''.join(circus_config).format(sample_rate, probe_file, p['template_width_ms'],
                    p['detect_threshold'], detect_sign, p['filter'], p['whitening_max_elts'],
                    p['clustering_max_elts'], auto)
        with (output_folder / (file_name + '.params')).open('w') as f:
            f.writelines(circus_config)

        if p['num_workers'] is None:
            p['num_workers'] = np.maximum(1, int(os.cpu_count()/2))

    def _run(self,  recording, output_folder):
        num_workers = self.params['num_workers']
        if 'win' in sys.platform:
            shell_cmd = '''
                        spyking-circus {recording} -c {num_workers}
                    '''.format(recording=output_folder / 'recording.dat', num_workers=num_workers)
        else:
            shell_cmd = '''
                        #!/bin/bash
                        spyking-circus {recording} -c {num_workers}
                    '''.format(recording=output_folder / 'recording.dat', num_workers=num_workers)

        shell_cmd = ShellScript(shell_cmd, keep_temp_files=True)
        shell_cmd.start()

        retcode = shell_cmd.wait()

        if retcode != 0:
            raise Exception('spykingcircus returned a non-zero exit code')

    @staticmethod
    def get_result_from_folder(output_folder):
        sorting = se.SpykingCircusSortingExtractor(folder_path=Path(output_folder) / 'recording')
        return sorting
