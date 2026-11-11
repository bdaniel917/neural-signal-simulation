# Neural Signal Simulation: design specification

Status: the double-precision acquisition-to-feature pipeline is implemented and validated for the included synthetic cases. This document also records broader design requirements and deferred work; it is not evidence that every proposed feature is implemented.

## Implementation status

- Implemented: common-clock source and analog approximation, ideal 16-bit ADC, full-rate/prefilter/multirate paths, causal bandpass and smoothed power, independent delay calibration, clean/noisy comparisons, selected alias tests, source/ADC checks, operation counts, and integrity inventories.
- Included evidence: `results/current_pipeline/` and `results/current_alignment_validation/`. These are the authoritative publication results.
- Deferred: float32/Q15/Q31 arithmetic, multichannel referencing and bad-channel handling, real recordings, hardware calibration, target timing/RAM/buffers/energy, broader stress coverage, and a formal 100-seed study.
- Numerical targets are project choices. Passing the included synthetic-case checks does not establish product or clinical performance.

The remaining sections retain the design rationale and intended extensions. References to earlier acquisition/notch work describe background; that older implementation is not included in this repository.

## 1. Purpose and problem

Design and evaluate a causal, streaming acquisition-to-feature pipeline that
preserves a known band-limited power feature under noise, interference, finite
precision, and rate changes. Determine when lower processing rates and narrower
arithmetic reduce resource requirements without unacceptable feature error,
latency, or data loss.

The existing model isolates acquisition and notch-filter effects. This extension
adds a defined downstream feature, explicit multirate processing, and resource
accounting. It does not attempt to reproduce a proprietary device or validate a
clinical decoder.

## 2. Known facts, assumptions, and constraints

- The current C11 simulator and Python analysis/validation remain the foundation.
- Existing regression: two RC poles, 93/183 Hz test tones, ADC and notch studies.
  Preserve these as legacy experiments; 183 Hz is intentionally outside the new
  70–150 Hz branch and cannot be treated as a desired in-band component there.
- There are no measured electrode voltages, amplifier transfer functions, ADC
  nonlinearity/jitter measurements, CPU target, clock, RAM limit, or product latency
  requirement supplied. Do not imply those quantities have been measured.
- Amplitude is normalized full scale (FS). ADC codes represent [-1,1). Power is
  FS². Noise is one-sided input-referred amplitude density in FS/sqrt(Hz).
- ADC rates: 1, 2, and 4 kHz. Internal analogue-model rate: common 80 kHz, with
  40/80/160 kHz convergence checks. This internal numerical clock is not a CPU clock.
- ADC widths: 12, 16, 24 bits. Arithmetic: double reference, float32, Q15, Q31.
  Eight-bit operation is optional stress only; 17-bit examples leave the main study.
- All deployed processing is causal and stateful. No forward/backward or centered
  zero-phase filtering may be used to claim streaming equivalence or latency.
- No allocation inside the processing loop; independent states per channel.
  Preserve histories and decimation phase across arbitrary block boundaries.
- First implementation uses controlled synthetic inputs. Recorded-data validation
  is a separate next step, not a prerequisite for validating numerical contracts.

## Nominal baseline configuration

| Parameter | Baseline |
|---|---|
| Channels / spatial reference | One channel / identity; eight-channel reference study is a separate experiment |
| Desired signal | 110 Hz carrier; A(t)=0.20[1+0.25cos(2 pi 2t)]; repeat with 5 Hz modulation |
| Input white noise density | 0.0002 FS/sqrt(Hz), one-sided, before gain |
| Line interference | 0.12 FS peak at 60 Hz; no drift or amplitude step |
| Harmonic / artifact / DC offset | Zero in nominal case; injected explicitly in stress cases |
| Out-of-band probe | 0.10 FS peak at 1350 Hz |
| Analogue response | Gain 1, candidate Butterworth from the stage requirements below |
| ADC | 2 kHz, 16 bits, ideal rounding/saturation |
| Processing architecture | Filtered decimation to 1 kHz |
| Band selection / line rejection | Specified 70–150 Hz filter; baseline notch OFF. Paired comparison adds 60 Hz Q=25; 120 Hz notch is a separate in-band signal-loss experiment |
| Feature / output rate | Smoothed squared signal with explicit output clamp, 100 Hz |
| Arithmetic | Double baseline; other formats are paired implementation comparisons |
| Blocks / record | 8 ms input blocks; 20 s record; common epoch and defined startup exclusion |
| Noise repetition | Explicit recorded seed; primary statistical study seeds 1..100 |
| ADC conversion/transport delay | Zero in functional baseline; separately declared if a delay model is added |

The ideal ADC is not a model of a particular converter's internal digital filters
or conversion latency. No analogue high-pass is assumed. DC offset can therefore
consume ADC headroom before digital band selection; test that explicitly rather
than claiming the digital high-pass restores clipped information.

## 3. Desired output and mathematical definition

Primary streaming output: one nonnegative smoothed bandpower estimate per valid
channel at 100 updates/s, representing activity in the 70–150 Hz band. This is
power, not a Hilbert amplitude envelope or classifier prediction.

Retain the filtered waveform at its actual processing sample rate as a separate
optional diagnostic output. It is not represented by the 100 Hz power stream.
Waveform streaming/storage costs must be counted when enabled; feature-rate
reduction does not reduce transport bandwidth if full-rate waveforms are still
transmitted alongside it.

Power is selected as an explainable engineering feature: known synthetic
amplitude modulation supplies an analytical power target; squaring and smoothing
are causal operations that can be implemented in fixed point. It is not asserted
to be the best neural decoder feature. The cited research's Hilbert-amplitude
feature is a different definition. Using power here is a project choice, not
reproduction of that exact research method. A²/2 is normalized mean square (FS²,
or V² with a voltage calibration), not watts without an electrical/load model.

For referenced channel waveform r[n]:

    b[n] = causal_bandpass_70_150(r[n])
    y[n] = optional_notch(b[n])  # identity in the baseline
    u[n] = y[n]^2
    raw_power[k] = causal_lowpass(u)[k R], R = processing_rate / 100
    power[k] = max(raw_power[k], 0)

The measured quantity is the mean square of a realizably filtered waveform, not
an exact rectangular 70–150 Hz FFT-bin integral. Finite filter rejection means
residual out-of-band components can contribute. It also includes in-band noise
and interference: it is not automatically an unbiased estimate of neural-only
power. The clean desired-power oracle is an evaluation reference, not information
available to a deployed estimator.

The clamp is an explicit output operation: a windowed FIR can have negative
coefficients and transient undershoot even though u is nonnegative. Preserve
raw_power and record clamp events; never conceal them as ordinary precision
noise. Compare numerical implementations with the identical clamp policy.

Secondary, optional log output:

    log_power[k] = 10 log10(max(power[k], 1e-12 FS²) / (1 FS²))

Label the reference explicitly as 1 FS²; do not assume this equals a different
full-scale-sine dBFS convention. Record floor application. Primary accuracy gates
use linear power, not the logarithm or clipping the error denominator.

Each output record contains channel ID, sequence number, acquisition-clock
feature timestamp, emission/availability time (if scheduler model is enabled),
raw_power_FS2, power_FS2, optional log_power, and quality flags. Flags distinguish
startup, ADC overload, numerical limit events, missing data, excluded reference
channels, output clamp, and logarithm floor. Retain flagged values diagnostically;
do not mix them silently into nominal accuracy results.

Nominal controlled input:

    s(t) = A(t) sin(2 pi 110 t)
    A(t) = 0.20 [1 + 0.25 cos(2 pi fmod t)], fmod = 2 or 5 Hz

For this single carrier the intended unfiltered cycle-mean power is A(t)^2/2.
Its modulation components extend to 2 fmod <=10 Hz. It gives an analytic target
without assuming powers of coherent multiple carriers always add. Also test
90 and 130 Hz carriers separately. Use multi-tone/broadband probes as additional
cases with independently specified references, including beat/cross terms.

Power references are after the declared analogue gain: multiply the input-power
oracle by G². The gain is one in the primary baseline. Spatial referencing changes
the desired waveform; use both original-channel and explicitly referenced-clean
power targets in array experiments.

## 4. Proposed architecture

    Synthetic desired signal + physical disturbances
        -> analogue gain and acquisition anti-alias response
        -> ADC (1/2/4 kHz; 12/16/24 bits)
        -> digital anti-alias FIR and optional decimation to 1 kHz
        -> spatial referencing on channel waveforms
        -> 70–150 Hz band-pass (IIR second-order sections)
        -> optional line-interference rejection
        -> square using a widened integer product; explicitly rescale
           into the power-filter format
        -> feature low-pass (FIR)
        -> feature decimation to 100 Hz
        -> explicit nonnegative clamp, flags, optional log

Single-channel referencing is identity. Compare the actual full-rate architecture
with the multirate architecture: single-rate band selection and squaring run at
the ADC rate, then feature filtering/decimation produces the SAME 100 Hz output.
Do not mistake the existing 80 kHz analogue integration clock for a digital
multirate processing implementation.

## 5. Stage requirements and rationale

| Stage | Proposed requirement | Reason / evaluation |
|---|---|---|
| Analogue acquisition response | Candidate continuous-time Butterworth, <=0.25 dB attenuation over 0–150 Hz, >=40 dB attenuation from 500 Hz upward; fixed response across ADC rates | Gives a defined analogue rejection target for the lowest ADC rate. Measure folded in-band power too: finite attenuation is not zero aliasing. |
| Legacy analogue response | Keep existing two 650 Hz RC poles as regression and deliberately weaker acquisition-rejection case | Do not claim the existing RC response meets the new anti-alias specification. Compare DSP architectures under the SAME selected analogue model. |
| ADC | Ideal rounding/saturation at 12/16/24 bits; common range, separate rounding and overload errors | Isolates resolution from gain and full-scale range. Nominal bit depth does not establish ENOB. |
| Digital acquisition decimator | For 2/4 ->1 kHz: pass 0–200 Hz, <=0.1 dB gain deviation; stop >=450 Hz, >=60 dB rejection; causal linear-phase polyphase FIR, unity DC gain | Preserve 70–150 Hz with transition margin below the new 500 Hz Nyquist limit. Validate response and actual folded interferers. |
| 1 kHz ADC case | No acquisition rate reduction | Already at common processing rate. Any filter added only for response matching must be declared rather than hidden. |
| Spatial reference | Before band selection/nonlinear features; none / mean of declared good channels / local good channels | Compare interference reduction and desired-signal loss separately. Initial quality masks are supplied for controlled faults, not inferred from future data. |
| Band-pass | Pass 70–150 Hz, <=1 dB passband attenuation; stop <=40 and >=200 Hz, >=40 dB rejection; unity peak gain convention; minimum-order Butterworth SOS baseline | Explicit finite transition bands. Filter order follows requirements, not an arbitrary number of biquads. All-format realized response must be remeasured. |
| Notch | Baseline OFF; paired 60 Hz Q=25 candidate; 60+120 Hz is a separate stress/design comparison. | 60 Hz lies in the specified band-pass transition region, not a guaranteed rejection band. Retain an added notch only if measured interference/feature error or internal headroom justifies its delay, distortion, and resource cost. A 120 Hz notch removes desired in-band activity. No automatic harmonic bank. |
| Feature low-pass | Pass 0–10 Hz, <=0.1 dB gain deviation; stop >=40 Hz, >=60 dB rejection; unity DC gain; causal odd-length linear-phase FIR | Preserves the controlled power modulation with guard before 50 Hz feature Nyquist. Smoothing is itself feature shaping and must be measured. |
| Feature rate | 100 Hz, common acquisition-clock epoch, continuous phase | Update interval is 10 ms, not total response latency. |

FIR order estimation is a starting point; verify dense frequency response, edge
frequencies, DC gain, and quantized coefficients, increasing order as needed.
A modest design margin (e.g. 70 dB design for a 60 dB requirement) is allowed and
must be recorded. Zero padding is a declared startup state, not future samples.

### Conditional notch decision and ordering

Measure band-pass-only output first. The initial project screen for an unwanted
component is <=1% isolated feature NRMSE relative to the desired active-power
reference, with all other settings and the desired signal held fixed. Also
measure internal peaks and limit events. A notch is a candidate remedy when this
screen/headroom fails, not a mandatory extra stage. If both designs pass, retain
band-pass-only unless a separately stated requirement favors the notch. Do not
select a notch merely because a full-band waveform SNR improves.

A residual out-of-band tone still contributes positive DC after squaring; the
feature low-pass cannot remove that mean-square term. For the candidate 1 kHz
Butterworth band-pass, a local calculation gives about 18.59 dB attenuation at
60 Hz. A .12 FS peak 60 Hz input then contributes approximately 0.48% of nominal
unfiltered desired mean power (analogue gain approximated as unity in this
illustration). This is an illustrative leakage calculation, not an end-to-end
validation result or a guarantee for stronger/drifting interference.

The first notch comparison places it after the band-pass, matching the analysis
branch definition. This is a comparison convention, not a claim that a notch
must follow a band-pass. For ideal LTI filters at the SAME sample rate, exchanging
their order leaves the combined transfer function unchanged. Finite precision
and internal saturation can change the outcome. Compare notch-before-band-pass
if headroom or numerical results motivate it, using identical coefficients and
inputs; record peak internal values, errors, transient behavior, and MAC counts.

Reference spatial masks are fixed per controlled experiment. Flat and artifact
channels can be injected. An automatic online bad-channel detector, recovery
hysteresis, and reference-membership transitions are deferred; whole-record
quality gates must not be presented as causal online detection. Compare an
all-channel reference as a deliberately contaminated-reference stress case.

## 6. Numerical contract

- Double: reference arithmetic and independently designed/reference-checked filters.
- Float32: store coefficients/state and execute the declared arithmetic in float32;
  document fused multiply-add/compiler behavior. Do not relabel double as float32.
- Q15/Q31: signed 16/32-bit signal representation with 15/31 fractional bits.
  Document section gains, coefficient scaling/postshift, input headroom, state
  widths, product format, accumulator width, MAC order, rounding, saturation,
  and every interstage conversion. The label describes signal representation;
  it does not mean every product or power value uses that same width.
- Squaring uses a widened product, followed by an explicitly specified conversion
  into the smoother's format. For Q15, X represents x=X/2^15, so X*X is a 32-bit
  product with 30 fractional bits. For Q31, the 64-bit product has 62 fractional
  bits. Promote operands BEFORE multiplication. Specify retained bits, shifts,
  rounding, saturation, and output units. Do not immediately discard the extra
  fractional information without measuring its effect on low-power inputs.
  Validate both low-level and end-to-end feature error.
- Use overflow-safe MAC operations; 64-bit storage alone is not proof of safe Q31
  accumulation. Python arbitrary integers provide a bit-accurate oracle.
- Saturation/nearest rounding is the primary contract. Truncation/wrap remain
  labeled stress modes, not baseline recommendations.
- Quantized linear poles must be inside the unit circle, but separately test
  limit cycles, internal headroom, saturation recovery, and feature-floor effects.
- The coefficient/design stage must emit an arithmetic/range contract and memory
  layout for EACH selected format before that implementation is accepted. A
  generic Q31 implementation is not automatically CMSIS-bit-identical.

## 7. Latency and rate-reduction cost

Project screening target: <=200 ms small-modulation feature delay for nominal
110 Hz carrier and 2/5 Hz modulation, reported for notch-off and 60 Hz candidates
separately. The 120 Hz notch is outside this nominal preservation screen. This is a provisional
engineering budget, not a biological or product requirement.

Compare ADC blocks of equal duration: 8 ms =8/16/32 samples at 1/2/4 kHz.
Process partial final blocks and maintain decimator phase independently of the
block size. Feature production can yield zero or multiple records per call.
Use causal sample timestamps t[n]=n/fs, with a shared epoch and defined phase-zero
decimation, so reference/architecture comparisons share a 100 Hz timestamp grid.
Do not hide availability/queueing time by backdating timestamps for filter delay.

Report separately:

1. Analogue and digital frequency-dependent group delay, evaluated in-band.
2. Linear-phase FIR delay: (L-1)/(2 fs).
3. Envelope/power modulation delay and distortion measured against the oracle.
4. Block collection delay, actual feature emission schedule, processing time,
   and any simulated queueing delay.
5. Step rise/settling and artifact recovery: these are NOT the same as group delay.

Do not sum IIR maximum group delay and call it a proven nonlinear feature latency.
Use that sum only for screening; measure complete feature response. Delay-aligned
accuracy is a diagnostic in addition to unaligned accuracy and explicitly reported
latency. Never align away the latency requirement itself.

Rate reduction may add acquisition anti-alias filter delay. It does not inherently
make all subsequent filters slower: maintaining physical bandwidth while scaling
FIR length with sample rate can keep time delay nearly unchanged. Compare feature
error / latency / MAC count / memory as a Pareto tradeoff; savings are not assumed.

## 8. Local feasibility check (design calculations only)

These are candidate calculations using installed SciPy; they are not validation
of an implemented pipeline or quantized realization.

- Analogue 0–150 Hz /500 Hz, .25/40 dB requirements give a fifth-order Butterworth
  response, corner about 198.985 Hz, maximum 70–150 Hz group delay about 3.64 ms.
- At 1 kHz, the 70–150 /40–200 Hz, 1/40 dB Butterworth band-pass requires eight
  SOS sections (order 16); its in-band group delay is about 17–50 ms.
- A candidate feature FIR designed with 70 dB Kaiser parameters needs 147 taps at
  1 kHz; group delay is 73 ms. At 2/4 kHz, comparable designs use 291/579 taps,
  delays 72.5/72.25 ms. Measured candidate stopband rejection was about 70 dB.
- Candidate 2/4 ->1 kHz anti-alias FIRs use 37/71 taps, delay 9/8.75 ms, with
  roughly 68 dB stopband rejection under the chosen design margin.

The 200 ms feature-delay target is plausible, but not established. The band-pass
is not just one or two biquads: its actual cost and quantized stability need work.
If the Butterworth design fails a useful resource/latency constraint, compare a
minimum-order Chebyshev-II SOS design under the SAME magnitude requirements;
do not silently loosen requirements or select a lower order by appearance.

## 9. Timing, buffering, and memory models

No target CPU is specified. Separate three kinds of evidence: algorithmic operation
counts, host benchmark timings, and hypothetical CPU-cycle scenarios. Never turn
host seconds into embedded target cycles by multiplying by an assumed frequency.

C counts operations at the rate of each stage, including rescaling, squaring,
reference computation, and conversions. A configurable cost table converts those
counts into ASSUMED cycles; report the table with results. Example CPU frequencies
50/100/200 MHz are scenarios, not claims about any actual processor. Service time
is assumed cycles/clock frequency. CPU utilization must include other declared
work or reserve; meeting a nominal deadline does not prove worst-case execution.

Virtual producer-consumer test: bounded ring buffer, one processing consumer,
fixed 8 ms acquisition blocks, fixed-capacity startup-empty queue, explicit
FIFO order, completion before same-time arrivals, drop-newest on full queue,
and configured stalls/preemptions. Capacity sweeps: 2/4/8/16 waiting blocks;
in-flight storage is counted separately. Compare no stall, an isolated 50 ms
stall, and 10 ms stall every 100 ms. These are hypothetical workloads.

A lost input block invalidates affected features. First version resets signal
filter history/decimation phase to the shared time epoch after the discontinuity,
marks startup invalid again, and reports the gap and recovery; it must not
silently filter nonadjacent samples as if continuous. A hardware DMA/concurrent
RTOS implementation is outside this virtual model.

Memory ledger: coefficient arrays (shared when identical), per-channel states,
input/output blocks including in-flight buffers, ring storage, power/filter
intermediates, feature records, flags, and temporary workspace. Report actual
host sizeof/alignment separately from proposed packed target formats. CSV trace
storage is debug/offline I/O, not embedded working RAM.

Resource scaling: 1/8/64/256/1024 channels. These are scaling scenarios, not device
channel-count requirements. No hard RAM/CPU pass limit until a target is chosen.

## 10. Outputs and evaluation

Artifacts: complete parameter/format manifest, filter coefficients and responses,
ADC and selected stage traces, 100 Hz feature records/flags, reference features,
per-trial metrics, paired summaries/intervals, operations and memory ledgers,
queue/latency traces, plots, and an updated engineering report/diagram.

Three reference levels:

- Analytic synthetic target A²(t)/2 (after gain) or declared referenced-clean target:
  total clean-path feature distortion, including analogue/band selection/smoothing.
- Clean double implementation of each actual architecture: acquisition disturbance
  effects, distinct from intentional filter response.
- Noisy double implementation versus the SAME-input float32/Q implementation:
  numerical error. Compare against an independent SciPy causal implementation
  before trusting C double as the reference.

Compare architectures on a common 100 Hz clock grid, matched physical passbands,
identical input/noise realization at shared analogue sample times, declared
spatial reference, and the same output definition. Different discretized filter
responses need not be sample-identical. Record response differences instead of
calling all differences numerical error.

Accuracy metrics: waveform SNR and in-band error, signed mean feature bias,
feature NRMSE (RMS error / RMS active reference feature), correlation as secondary,
2/5 Hz modulation gain/phase, residual line/harmonic power, alias rejection,
negative raw-power/clamp/floor counts, ADC/internal limit events, and recovery.
Use absolute RMS when the reference is zero; relative error at silence is undefined.

Illustrative nominal-screen targets (not automatic gates for deliberate stress):

| Check | Initial screening target |
|---|---|
| Designed filter magnitude response | Meets the stage table in double; separately recheck every numeric realization |
| Nominal ADC and numeric overflow | Zero observed events in defined nominal records; not a theoretical Gaussian tail guarantee |
| Clean primary-carrier feature bias | <=10% absolute mean bias against analytic target, stated alignment policy |
| Float32 numerical feature NRMSE | <=0.1% versus same-architecture double |
| Q15/Q31 numerical feature NRMSE | <=1% versus same-architecture double; a failure is a result, not permission to alter the oracle |
| Multirate vs full-rate clean feature NRMSE | <=2% for the nominal 110 Hz carrier and 2/5 Hz modulation after fixed clean-calibration alignment; separately report unaligned error. Not a universal bound for every band-edge input |
| Feature delay | <=200 ms nominal small-modulation delay; report both modulation frequencies and separate transient behavior |
| Block/reference equivalence | Same output for varied block boundaries within each arithmetic contract and sample phase |
| Gap/overrun accounting | Exact conservation of produced, processed, waiting, in-flight, and dropped blocks |
| Working memory | Allocated byte totals agree with the declared layout; no in-loop allocations |

No global pass label combines these into a product claim. Stage errors and
feature error can fail different criteria; both must remain visible.

## 11. Experiments and statistics

Use staged experiments instead of the Cartesian product of every setting:

1. Deterministic unit/analytical checks, impulse/step/sweep/rounding/overflow probes,
   causal SciPy reference comparisons, and block/decimation-phase equivalence.
2. Double, ADC16, gain1, no spatial reference: full-rate versus multirate at 1/2/4 kHz.
3. ADC12/16/24 with selected architecture; Q15/Q31/float32 under identical ADC input.
4. Eight synthetic channels: known shared interference and desired activity,
   declared quality masks, none/good-average/local references, contaminated-average
   stress. Label matched-reference and original-channel preservation separately.
5. Stress: low amplitudes (.002/.02/.2 FS scale), DC/drift, carriers near band edges
   and 120 Hz, line frequency offset/drift/harmonics, ADC-folding tones such as
   900 Hz at 1 kHz ADC, overload, startup, gaps, and zero-input limit cycles.
6. Resource/buffer scaling using measured operation counts and declared timing
   assumptions; avoid simulating thousands of identical waveforms just to scale RAM.
7. One hundred independent noise seeds for primary paired comparisons. Reuse each
   seed/physical realization across the paired architectures. Parameter-variation
   priors, if added, must be separately specified and called hypothetical sensitivity.

Default nominal record 20 s, with at least 10 s valid analysis after startup.
Warm-up begins with the slowest-pole decay estimate plus FIR support and is
confirmed by measured clean impulse/step response; fixed-point limit cycles
cannot simply be discarded as startup. Extend stress records for recovery.

Compute trial-level metrics first. Report means, SD, median, empirical p05/p95,
and paired trial differences. Bootstrap 95% confidence intervals by resampling
independent trial pairs (fixed bootstrap seed, e.g. 2000 resamples). Feature
samples and correlated channels are not independent trial replicates. Empirical
percentiles are not confidence intervals or manufacturing yields. Limit-cycle
and overload tests are deterministic named cases, not evidence of population rates.

## 12. Independent-viewer review: additional decisions and open items

### A. Requirements are project choices, not measured necessities

70–150 Hz is an illustrative high-gamma branch motivated by published research;
110 Hz keeps the nominal AM sidebands well inside that band. The power feature
with 5 Hz amplitude modulation includes components to 10 Hz, explaining the
feature passband. A 100 Hz update rate is a convenient ten-samples-per-10-Hz-cycle
choice compatible with all selected ADC rates, not a proven optimal rate.

The 200 Hz acquisition-decimator pass edge leaves 50 Hz above the desired band;
450 Hz stop edge leaves 50 Hz before the 1 kHz output's Nyquist frequency. The
feature stop edge at 40 Hz leaves 10 Hz before the 100 Hz output's Nyquist limit.
The .1/1 dB and 40/60 dB limits, 100 trials, and 200 ms budget are initial study
screens, not biologically established requirements. Record sensitivity and
revise them openly if measured feature/latency tradeoffs justify revision; do not
present them as unique correct choices.

### B. Same specifications do not imply identical architectures

Meeting a 1 dB passband bound does not guarantee feature agreement within 2%.
At one frequency a 1 dB magnitude difference can imply about a 21% power loss.
Different-rate minimum-order designs may have different orders and responses.
The 2% comparison screen therefore applies to the defined nominal signal only;
band-edge and broadband cases report response and feature differences rather
than assuming universal sample equivalence.

Use three double-precision controls at each 2/4 kHz ADC rate:
1. Full-rate feature pipeline without the added acquisition-decimator FIR.
2. Full-rate pipeline WITH that same FIR but WITHOUT sample removal.
3. FIR plus decimation, with downstream processing at 1 kHz.

Controls 1/2 isolate the extra FIR's effect. Controls 2/3 compare rate/ downstream
realization effects under the same prefilter. Redesign rate-dependent filters
against the same physical requirements, and report realized response differences.
At 1 kHz ADC the two architecture paths are identical unless an explicitly named
control adds an extra filter. Do not invent a decimation benefit for factor one.

### C. Alias budgets need feature-level checks

Stopband attenuation alone does not bound contamination without interferer levels
and frequencies. In isolated nominal-amplitude tests, inject a .10 FS peak tone
and compare feature output with/without that tone: initial screen <=1% feature
NRMSE relative to the desired active-power oracle. Sweep frequencies that fold
into 70–150 Hz, including neighborhoods of k*fs +/- the desired band, within the
simulated source bandwidth. Repeat for acquisition and digital decimation.
Report folded amplitudes, feature bias, and failures; do not use a noise floor to
hide a deterministic alias. Larger interferers are separately labeled stress.
Shared 80 kHz simulation time/noise realizations and convergence checks control
numerical artifacts; they do not establish rejection of unmodeled frequencies.

### D. Make latency identification unambiguous

A single 5 Hz phase measurement has a 200 ms ambiguity; an apparent zero phase
could conceal one full cycle of delay. Use separate clean calibration records,
a modulation-frequency sweep (e.g. 1–10 Hz) with continuity-based phase unwrapping,
and an onset/step check to resolve lag. Distinguish frequency-dependent modulation
phase from a single pure transport delay.

Choose diagnostic alignment from the independent clean calibration BEFORE noise
trials and hold it fixed for that architecture/test condition. Do not optimize
cross-correlation lag separately on each noisy trial. Keep the original feature
and availability timestamps and report unaligned accuracy/latency too.

### E. Quality flags cannot improve a score by hiding failures

After the declared startup interval, fixed analysis windows and reference masks
are chosen before seeing numeric outcomes. Report total expected features,
valid coverage, each invalid-reason count, and recovery. Nominal screens require
no ADC/internal limit events and no unplanned invalid coverage. Stress reports
show both fixed-window diagnostic error and valid-only error/coverage, including
clamp/floor effects. Do not report excellent accuracy from a tiny surviving subset.
Clamps and logarithm floors are not mechanisms for making negative/error values
invisible: retain raw smoother error and event counts alongside delivered power.

### F. Referencing conventions and zero references must be explicit

Common-average reference includes the channel being processed in the declared
reference set; local reference excludes that channel and names the neighbor set.
Single-channel baseline is identity, not a one-channel average subtracted from
itself. For array reference experiments, declare fully shared, independent, and
mixed desired spatial components, their phases/amplitudes, and the supplied
fault/reference mask. Do not assume referenced-channel power equals the original
channel power or that coherent component powers simply add.

An empty reference set yields invalid output for that reference configuration,
not an undocumented fallback. A true zero desired feature uses absolute error;
relative error/NRMSE and correlation are undefined and must be marked accordingly.
Array sampling is assumed synchronous; interchannel timing skew and automated
quality detection remain outside the first prototype.

### G. ADC and arithmetic comparisons must not confound one another

Study ADC widths using double arithmetic first. For arithmetic comparisons,
feed exactly the SAME saved ADC codes to every realization and report input
format-conversion error separately from recurrence/feature error. A Q15 input
conversion can discard information from a 24-bit ADC; that is a result, not a
failure of the ADC. Coefficient ordering/scaling and peak intermediate values are
required design outputs, not optional implementation details.

### H. Scope, resource claims, and conclusions

Separate feature-only and feature-plus-waveform output modes in throughput and
memory accounting. Keep the old analogue/notch regression separate from fair
comparisons within the new analogue response. Do not attribute simultaneous
analogue-model and digital-pipeline improvements solely to multirate processing.

Stages 1–4 of implementation establish signal/feature correctness and multirate
comparisons. Referencing, numerical formats, and virtual scheduling follow as
independently validated extensions. Avoid a full factorial experiment across all
rates, masks, widths, channel counts, and stalls before the core is understood.
No decoder, online adaptive notch/channel detector, physical jitter, actual RTOS,
or power-consumption claim is included. Those are explicit scope limits, not
silently solved requirements.

### I. Noise bias and feature-definition consistency

Include noise-only and zero-input records. For uncorrelated additive noise, the
expected squared output contains both signal and filtered-noise power. Do not
interpret a positive feature during silence as recovered neural activity, or
silently subtract a noise floor estimated using the test's known clean target.
Any noise-debiased variant is a separately named estimator with its own calibration
assumptions, validity range, and bias/variance analysis; it is not baseline behavior.

Offline FFT bandpower and the causal filtered-square feature have different
frequency weighting and temporal support. They can be reported side by side,
but must not be substituted for each other as an exact reference. An amplitude
feature is also different from power: if explored later, use its proper units,
reference, and nonlinear transform rather than relabeling the existing output.

### J. Statistical scope

Report the number of nominal trials passing each screen as well as metric
intervals. Zero observed failures in 100 trials does not prove zero failure
probability. A failure-rate confidence statement needs a separately specified
binomial interval and independence assumptions; the feature-mean bootstrap does
not supply that statement. Do not claim narrow tail or worst-case guarantees
from the proposed sample count.

Remaining implementation/design work before numerical acceptance: exact section
gains and coefficient representations; per-stage state/product/accumulator widths;
rounding and overflow points; filter coefficients and realized responses; and
complete memory/layout and operation counts. Remaining external unknowns: actual
hardware calibration, useful physiological features, target CPU/RAM, and product
latency requirements. Neither category is solved by approving this specification.

## 13. Implementation sequence and limits of specification

1. Freeze this feature/magnitude/timestamp contract and preserve legacy regressions.
2. Design candidate double-precision filters and export exact coefficients/orders,
   measured responses, scaling/range contracts, and a stage delay budget.
3. Implement causal stateful single-rate C; validate against analytical/SciPy oracles.
4. Add decimation and verify paired architecture comparisons and timestamp phases.
5. Add referencing and controlled bad-channel cases before nonlinear features.
6. Add actual float32/Q15/Q31 and bit-accurate numerical checks.
7. Add operation/memory ledgers and virtual buffer/timing experiments.
8. Run the staged study; update report and website only from checked artifacts.

This is sufficient for an explainable prototype once the project-level proposed
thresholds are accepted. It is not a production specification: hardware calibration,
real neural feature relevance, target cycle counts, RAM constraints, and product
latency/quality requirements are still unknown. Exact SOS scaling, coefficient
formats, filter lengths, and quantized ranges are design outputs with explicit
acceptance checks, not numbers to guess before designing the filters.

## References

- Precision-associated research example (specific research workflow, not a claim
  about the current production chain): https://www.nature.com/articles/s41551-025-01501-w
- IIR design from pass/stop requirements: https://docs.scipy.org/doc/scipy/reference/generated/scipy.signal.iirdesign.html
- FIR order estimation: https://docs.scipy.org/doc/scipy/reference/generated/scipy.signal.kaiserord.html
- FIR design and delay: https://docs.scipy.org/doc/scipy/reference/generated/scipy.signal.firwin.html
- Causal FIR decimation implementation pattern: https://arm-software.github.io/CMSIS-DSP/main/group__FIR__decimate.html
