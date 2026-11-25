# Export one simulated KomaMRI volume with its acquisition times, physical k-space and gradient.
# In a Julia workshop session: include("export_koma.jl"); export_koma_epi(folder, seq, raw; b_value=0)
# To recreate the point pair: julia --project=<workshop-environment> export_koma.jl OUTPUT [SEQUENCE.seq]
# Default sequence: JuliaHealth/KomaMRI.jl v0.15.0, examples/1.sequences/epi_ramp.seq.
using KomaMRICore, DelimitedFiles

function export_koma_epi(folder, seq, raw; b_value, rep=nothing, slice=nothing,
                         nx=Int(seq.DEF["Nx"]), ny=Int(seq.DEF["Ny"]), fov=seq.DEF["FOV"])
    ctx = adc_label_context(seq)
    profiles = raw.profiles
    @assert length(profiles) == length(ctx.adc_blocks) "Use the original simulated raw/sequence pair"
    imaging = Set(ctx.imaging_blocks)
    ids = findall(ctx.adc_blocks) do b
        l = ctx.labels[b]
        b in imaging && (isnothing(rep) || l.REP == rep) && (isnothing(slice) || l.SLC == slice)
    end
    isempty(ids) && error("No imaging profiles for this REP/SLC selection")
    times = get_adc_sampling_times(seq)                 # seconds, sample centers
    _, k = get_kspace(seq)                              # cycles/m, all ADCs, physical axes
    ends = cumsum([seq.ADC[b].N for b in ctx.adc_blocks])
    @assert size(k, 1) == length(times) == last(ends)
    rows = map(ids) do i
        p = profiles[i]
        n = seq.ADC[ctx.adc_blocks[i]].N
        @assert size(p.data) == (n, 1) "Expected one receive channel and all ADC samples"
        @assert iszero(p.head.discard_pre) && iszero(p.head.discard_post) "Trim discards consistently first"
        j = (ends[i] - n + 1):ends[i]
        s = p.data[:, 1]                                # acquisition order; complex samples
        hcat(fill(i, n), times[j], k[j, 1:3], real.(s), imag.(s))
    end
    gx = get_samples(seq).gx                            # waveform knots in s and T/m
    mkpath(folder)
    writedlm(joinpath(folder, "adc.tsv"), reduce(vcat, rows), '\t')
    writedlm(joinpath(folder, "gx.tsv"), hcat(gx.t, gx.A), '\t')
    writedlm(joinpath(folder, "geometry.tsv"), [nx ny fov[1] fov[2] γ b_value], '\t')
    return folder
end

using KomaMRIFiles

function generate_point_pair(folder, path)
    seq = read_seq(path)
    sys = Scanner()
    obj = Phantom(x=[0.035], y=[-0.021])
    params = Dict{String, Any}("gpu" => false, "Nthreads" => 1, "precision" => "f64")
    raw = simulate(obj, seq, sys; sim_params=params)
    export_koma_epi(joinpath(folder, "julia_b0"), seq, raw; b_value=0)
    # The second signal has a controlled exp(-bD) attenuation on the same readout.
    obj.ρ .*= exp(-1000 * 0.0008)
    raw_dw = simulate(obj, seq, sys; sim_params=params)
    export_koma_epi(joinpath(folder, "julia_dw"), seq, raw_dw; b_value=1000)
end

if abspath(PROGRAM_FILE) == @__FILE__
    using Downloads
    import KomaMRIFiles: SHA
    length(ARGS) in (1, 2) || error("Usage: julia export_koma.jl OUTPUT [pinned_epi_ramp.seq]")
    url = "https://raw.githubusercontent.com/JuliaHealth/KomaMRI.jl/v0.15.0/examples/1.sequences/epi_ramp.seq"
    mktempdir() do tmp
        path = length(ARGS) == 2 ? ARGS[2] : Downloads.download(url, joinpath(tmp, "epi_ramp.seq"))
        digest = bytes2hex(open(SHA.sha256, path))
        digest == "e0c3c253a3588b6eb0ad8586b55180afb83aa4d069adcea6720f8465435eed7a" ||
            error("Expected the published KomaMRI v0.15.0 ramp-EPI example")
        generate_point_pair(ARGS[1], path)
    end
end
