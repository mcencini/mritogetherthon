# Day 2 · Reconstructing diffusion-weighted EPI

Open **day2_dwi_epi_reconstruction.ipynb** for the original Python notebook. Its saved outputs let you compare your reconstructions with the workshop results.

## Run in the hackathon image

1. The environment downloads this folder to `~/material/handson/day2/reconstruction`, and copies it to your team's `day2/reconstruction` once your team is set up.
2. In JupyterLab, open the `reconstruction` folder and the notebook inside it. Keep the notebook beside the Python helper files and the `data` folder.
3. Select the Python 3 kernel, then choose **Kernel → Restart Kernel and Run All Cells**.

The exercises use the bundled data and run offline. They require NumPy, SciPy, Matplotlib and the Berkeley Advanced Reconstruction Toolbox (BART) command-line executable. To check that the container can find BART, open a JupyterLab terminal and run `bart version`.

For a command-line test, run the following inside your team's copy of the `reconstruction` folder (the one in `~/material` is read-only). It writes a separate notebook containing your test outputs.

```sh
jupyter nbconvert --to notebook --execute day2_dwi_epi_reconstruction.ipynb \
  --ExecutePreprocessor.kernel_name=python3 --ExecutePreprocessor.timeout=600 \
  --output day2_dwi_epi_tested.ipynb
```

## What to look for

- **Sequence-matched phantom.** The supplied sequence acquires 48 of 64 phase-encode lines. The simulated echoes include an added readout delay and even–odd phase error. The b=0 fit gives approximately **2.82 µs** and **0.745 rad**. Apply that fit to b=500 and estimate each volume’s own image phase for partial Fourier reconstruction.
- **Real brain EPI/DWI data.** Compare the full-band reference with reconstructions that omit one step at a time, including parallel imaging reconstruction.
- **Further exercises.** Run the multishot example, the off-isocenter spin-echo phase check, the directional ADC fits and the public Siemens navigator example.

## Files

| Location | Contents |
| --- | --- |
| `data/` | Prepared phantom echoes, real brain EPI/DWI excerpt, off-isocenter results and the public Siemens `epi.dat` with its read index and license. |
| Python files beside the notebook | BART interface, reconstruction routines and plotting functions imported by the notebook. |
| `figures/` | Standalone copies of selected notebook figures. All figures also appear in the executed notebook. |
| `preparation/` | Original Pulseq sequence archive, simulation and data-preparation code, and a Julia exporter for KomaMRI echoes. |
| `requirements.txt` | Python dependencies for running the notebook and the command-line test in a separate environment. Install BART as a system executable in that environment. |

The prepared signals are ready to load. For optional regeneration, `preparation/generate_sequence_dwi.py` uses PyPulseq and scikit-image to build the sequence-matched phantom series. The Julia worked example uses KomaMRI. Their dependencies are listed in the corresponding scripts.
