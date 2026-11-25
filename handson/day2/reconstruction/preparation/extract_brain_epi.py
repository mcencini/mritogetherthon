"""Regenerate the numeric teaching excerpt from the original real brain EPI/DWI TWIX acquisition with twixtools.

Usage: python extract_brain_epi.py input.dat data/brain_dwi_epi.npz
The workshop notebook uses the pre-extracted file and does not need twixtools.
"""
from pathlib import Path
import numpy as np


def extract(scan, dest, slice_index=12):
    groups = {k: [] for k in ('im0', 'im1', 'nav0', 'nav1', 'acs', 'acs_nav')}
    offset, channels = [], None
    for b in scan['mdb']:
        if b.cSlc != slice_index or b.cRep not in (0, 1):
            continue
        ref, nav = b.is_flag_set('PATREFSCAN'), b.is_flag_set('PHASCOR')
        if ref:
            kind = 'acs_nav' if nav else 'acs'
        elif nav:
            kind = f'nav{b.cRep}'
        elif b.is_image_scan():
            kind = f'im{b.cRep}'
        else:
            continue
        channel_ids = [int(h.ChannelId if hasattr(h, 'ChannelId') else h['ulChannelId'])
                       for h in b.channel_hdr]
        order = np.argsort(channel_ids)
        if channels is None:
            channels = np.asarray(channel_ids)[order]
        assert np.array_equal(channels, np.asarray(channel_ids)[order])
        ro_offset = b.mdh.ReadOutOffcentre if hasattr(b.mdh, 'ReadOutOffcentre') else b.mdh['fReadOutOffcentre']
        offset.append(float(ro_offset))
        groups[kind].append((b.data[order].T.copy(), int(b.cLin), -1 if b.is_flag_set('REFLECT') else 1))

    assert len(set(offset)) == 1 and len(channels) == 32
    payload = {}
    for label, kinds in [('im', ['im0','im1']), ('nav', ['nav0','nav1']),
                         ('acs',['acs']), ('acs_nav', ['acs_nav'])]:
        data = [np.stack([e[0] for e in groups[k]]) for k in kinds]
        ky = [np.asarray([e[1] for e in groups[k]], dtype=np.int16) for k in kinds]
        pol = [np.asarray([e[2] for e in groups[k]], dtype=np.int8) for k in kinds]
        wrap = np.stack if len(kinds) > 1 else lambda x: x[0]
        payload.update({label+'_adc':wrap(data), label+'_ky':wrap(ky), label+'_pol':wrap(pol)})
    assert payload['im_adc'].shape == (2,64,256,32) and payload['nav_adc'].shape == (2,3,256,32)
    assert np.all(payload['im_ky'] == np.arange(0,128,2)) and np.array_equal(payload['acs_ky'],np.arange(32,96))
    assert payload['acs_nav_adc'].shape == (3,256,32)
    y,m = scan['hdr']['MeasYaps'], scan['hdr']['Meas']
    assert y['sFastImaging']['lSegments']==1 and y['sSliceAcceleration']['lMultiBandFactor']==1
    assert y['sPat']['lAccelFactPE']==2 and y['sKSpace']['lPhaseEncodingLines']==128
    assert np.array_equal(m['alBValue'][:2], [0, 1000])
    timing = [m[key][0] for key in ('alRegridRampupTime','alRegridFlattopTime','alRegridRampdownTime',
                                    'alRegridDelaySamplesTime','aflRegridADCDuration')]
    payload.update(timing_us=np.asarray(timing), fov_mm=y['sSliceArray']['asSlice'][slice_index]['dReadoutFOV'],
                   offset_mm=offset[0], base_matrix=128, nky=128, acceleration=2, slice_index=slice_index,
                   b_values=np.asarray([0., 1000.]), physical_channel_ids=channels.astype(np.int16))
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(dest, **payload)
    return dest


if __name__ == '__main__':
    import argparse
    import twixtools
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source'); parser.add_argument('dest'); args = parser.parse_args()
    scan = twixtools.read_twix(args.source, include_scans=[1], parse_geometry=False)[-1]
    extract(scan,args.dest)
