"""Create a copy of a .seq file that mimics a gradient hardware delay (for simulation only).

Gradients arriving `delay` seconds late relative to the ADC is the same as the ADC starting
`delay` seconds early, so every ADC event is moved forward by `delay`.
Simulate the copy (simulate.py does it) and reconstruct with the ORIGINAL .seq file.

usage: python tools/simulation/make_hw_delay_seq.py <in.seq> <out.seq> <delay_s>      (e.g. 3e-6 = 3 us)
"""

import sys

import pypulseq as pp


def shift_adcs(seq_in, seq_out, delay):
    """Write a copy of seq_in with every ADC moved by -delay [s]. Returns the number of ADCs."""
    seq = pp.Sequence()
    seq.read(str(seq_in))
    n = 0
    for i in seq.block_events:
        block = seq.get_block(i)
        if block.adc is None:
            continue
        new_delay = block.adc.delay - delay
        adc_end = new_delay + block.adc.num_samples * block.adc.dwell
        if new_delay < 0 or adc_end > block.block_duration + 1e-9:
            limit = block.adc.delay if delay > 0 else block.block_duration - (block.adc.delay + block.adc.num_samples * block.adc.dwell)
            raise ValueError(f'a gradient delay of {delay * 1e6:g} us does not fit: the ADC can be shifted by at most '
                             f'{limit * 1e6:.0f} us in this sequence (realistic delays are a few us, e.g. 3e-6)')
        block.adc.delay = new_delay
        events = [e for e in (block.rf, block.gx, block.gy, block.gz, block.adc) if e is not None]
        events += list(getattr(block, 'label', {}).values()) if isinstance(getattr(block, 'label', None), dict) else []
        seq.set_block(i, *events)
        n += 1
    seq.write(str(seq_out))
    return n


if __name__ == '__main__':
    seq_in, seq_out, delay = sys.argv[1], sys.argv[2], float(sys.argv[3])
    n = shift_adcs(seq_in, seq_out, delay)
    print(f'{n} ADCs shifted by {-delay * 1e6:.2f} us -> {seq_out}')
