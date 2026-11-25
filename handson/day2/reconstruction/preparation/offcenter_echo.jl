# julia --project=<KomaMRI environment> preparation/offcenter_echo.jl \
#     path/to/epi_se_rs_multi_slice.seq data/offcenter_echo.csv
# Validated with KomaMRIBase 0.15.2, KomaMRICore 0.14.0 and KomaMRIFiles 0.12.0.
using KomaMRIBase, KomaMRICore, KomaMRIFiles

wrapped_deg(x) = rad2deg(angle(cis(x)))

function read_slices(path)
    seq = read_seq(path; verify_signature=true)
    seq.DEF["signature"].hash == "73848a9bf8837de0212a44624e3cb89e" ||
        error("Expected the supplied five-slice sequence")
    starts = findall(i -> seq.RF[1, i].use isa Excitation && is_RF_on(seq[i]), 1:length(seq))
    @assert length(starts) == seq.DEF["NSlices"] == 5
    shots = []
    for (j, first_rf) in enumerate(starts)
        last_block = j < length(starts) ? starts[j + 1] - 1 : length(seq)
        last_adc = findlast(i -> seq.ADC[i].N > 0, first_rf:last_block) + first_rf - 1
        shot = deepcopy(seq[first_rf:last_adc])
        rf = findall(i -> is_RF_on(shot[i]), 1:length(shot))
        @assert length(rf) == 2 && shot.RF[1, rf[2]].use isa Refocusing
        @assert all(a -> iszero(a.Δf) && iszero(a.ϕ), shot.ADC)
        # Infer the slice center from its transmit offset and slice-select gradient.
        g_hz_m = γ * shot.GR[3, rf[1]].A
        z_mm = round(1000 * shot.RF[1, rf[1]].Δf / g_hz_m; digits=3)
        ctx = adc_label_context(shot)
        slice_id = only(unique(ctx.labels[b].SLC for b in ctx.imaging_blocks))
        push!(shots, (; shot, rf, z_mm, slice_id, order=j))
    end
    return shots
end

function echoes(shot, z_mm)
    obj = Phantom(x=[0.0], y=[0.0], z=[z_mm / 1000])
    params = Dict{String, Any}("gpu"=>false, "Nthreads"=>1, "precision"=>"f64",
                                "Δt_rf"=>2e-6, "return_type"=>"mat")
    signal = vec(simulate(obj, shot, Scanner(); sim_params=params))
    ctx = adc_label_context(shot)
    ranges = cumsum([shot.ADC[b].N for b in ctx.adc_blocks])
    _, k = get_kspace(shot)
    @assert length(signal) == last(ranges) == size(k, 1)
    centers = Int[]
    for b in ctx.imaging_blocks
        j = findfirst(==(b), ctx.adc_blocks)
        idx = (ranges[j] - shot.ADC[b].N + 1):ranges[j]
        push!(centers, idx[argmin(abs.(k[idx, 1]))])
    end
    @assert length(centers) == shot.DEF["NyMeasured"]
    return signal[centers], argmin(abs.(k[centers, 2]))
end

function run(path, output)
    slices = read_slices(path)
    center = only(filter(s -> iszero(s.z_mm), slices))
    base_phase = [center.shot.RF[1, i].ϕ for i in center.rf]
    base_echoes, base_line = echoes(center.shot, 0.0)
    reference = base_echoes[base_line]
    # Additional position for which the phase difference does not wrap to zero.
    shifted = (; shot=deepcopy(center.shot), rf=center.rf, z_mm=1.0, slice_id=-1, order=-1)
    for (j, i) in enumerate(shifted.rf)
        event = shifted.shot.RF[1, i]
        event.Δf = γ * shifted.shot.GR[3, i].A * shifted.z_mm / 1000
        # Pulseq centers are 1.5 and 3 ms relative to the RF event start.
        # Koma's first RF sample occurs half a raster later for the excitation.
        t_center = (1.5e-3, 3e-3)[j]
        event.ϕ = base_phase[j] - 2π * event.Δf * t_center
    end

    open(output, "w") do io
        println(io, "case,z_mm,predicted_deg,simulated_deg,relative_magnitude,phase_on_vs_center_deg,phase_off_vs_center_deg,max_line_deviation_deg,on_real,on_imag,off_real,off_imag,slice_id,acquisition_order,even_odd_change_deg")
        for ex in [sort(slices; by=s -> s.z_mm); shifted]
            off = deepcopy(ex.shot)
            delta = [ex.shot.RF[1, i].ϕ - base_phase[j] for (j, i) in enumerate(ex.rf)]
            for (j, i) in enumerate(ex.rf)
                off.RF[1, i].ϕ = base_phase[j]  # retain both slice-select frequencies
            end
            a, line = echoes(ex.shot, ex.z_mm)
            b, _ = echoes(off, ex.z_mm)
            ratio = a .* conj.(b)
            @assert abs(a[line]) > 0.8 && abs(b[line]) > 0.8
            prediction = 2 * delta[2] - delta[1]
            @assert abs(wrapped_deg(angle(ratio[line]) - prediction)) < 1
            variation = maximum(abs.(wrapped_deg.(angle.(ratio .* conj(ratio[line])))))
            @assert variation < 0.1
            even_odd = rad2deg(angle(sum(ratio[2:2:end]) * conj(sum(ratio[1:2:end]))))
            kind = ex.order < 0 ? "shifted" : "supplied"
            values = (kind, ex.z_mm, wrapped_deg(prediction), rad2deg(angle(ratio[line])),
                      abs(a[line]) / abs(b[line]), rad2deg(angle(a[line] * conj(reference))),
                      rad2deg(angle(b[line] * conj(reference))), variation,
                      real(a[line]), imag(a[line]), real(b[line]), imag(b[line]),
                      ex.slice_id, ex.order, even_odd)
            println(io, join(values, ','))
        end
    end
end

length(ARGS) == 2 || error("Supply the five-slice .seq file and the output CSV path")
run(ARGS...)
