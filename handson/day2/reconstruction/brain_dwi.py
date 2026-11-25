"""Real brain EPI/DWI reconstruction with native navigator calibration, ramp sampling correction and GRAPPA."""
from dataclasses import dataclass

import numpy as np
from scipy import fft, linalg
from scipy.optimize import minimize_scalar


def load_brain_data(path):
    with np.load(path, allow_pickle=False) as f:
        return {k: f[k] for k in f.files}


@dataclass
class Geometry:
    t: np.ndarray           # ADC sample centers, microseconds
    target: np.ndarray      # Cartesian readout, cycles/m
    up: float
    flat: float
    down: float
    scale: float            # plateau dk/dt, cycles/m per microsecond
    origin_area: float
    offset_m: float

    def area(self, t):
        """Integral of the unit-amplitude trapezoid, in microseconds."""
        t = np.asarray(t)
        u = np.clip(t, 0, self.up)
        plateau = np.clip(t-self.up, 0, self.flat)
        d = np.clip(t-self.up-self.flat, 0, self.down)
        return u*u/(2*self.up) + plateau + d - d*d/(2*self.down)

    def native_kx(self, polarity, delay_us=0.):
        return polarity * self.scale * (self.area(self.t-delay_us) - self.origin_area)


def readout_geometry(d):
    up, flat, down, start, duration = d['timing_us']
    n = d['im_adc'].shape[2]
    t = start + (np.arange(n)+.5)*duration/n
    # The oversampled Cartesian FFT covers twice the prescribed image FOV.
    dk = 1/(2 * float(d['fov_mm']) / 1000)
    target = (np.arange(n) - (n-1)/2) * dk
    g = Geometry(t, target, up, flat, down, 1., 0., float(d['offset_mm'])/1000)
    unit_gradient = np.clip(np.minimum(t/up,(up+flat+down-t)/down),0,1)
    # Siemens normalizes the sampled trapezoid to base matrix / prescribed FOV,
    # then places the mean of the central ADC pair at kx=0.
    width = float(d['base_matrix'])/(float(d['fov_mm'])/1000)
    g.scale = width/(unit_gradient.sum()*duration/n)
    g.origin_area = g.area(t[n//2-1:n//2+1]).mean()
    return g


@dataclass(frozen=True)
class NavFit:
    delay_us: float
    phase_rad: float         # positive minus negative readout
    coherence: float


def _demodulated(adc,g,delay_us):
    # Siemens frequency offset assumes a constant plateau. Correct to the integrated trajectory
    # in acquisition order before flipping the reflected ADC records (twixtools perform_regrid).
    flat_k = (g.t-g.t.mean())*g.scale
    actual_k = g.native_kx(1, delay_us)
    rotation = np.exp(2j*np.pi*g.offset_m*(flat_k-actual_k))
    return adc * rotation[:,None]


def linear_regrid(k, adc, target):
    """Linear interpolation of complex ADC samples along the penultimate (readout) axis."""
    if k[0] > k[-1]:
        k, adc = k[::-1], adc[..., ::-1, :]
    j = np.clip(np.searchsorted(k,target)-1, 0, len(k)-2)
    w = (target-k[j])/(k[j+1]-k[j])
    out = (1-w[:, None])*adc[...,j,:] + w[:,None]*adc[...,j+1,:]
    # Outside measured support there are no bracketing samples for linear interpolation.
    out[..., (target < k[0]-1.e-8) | (target > k[-1]+1.e-8), :] = 0
    return out


def _fit_nav(adc, pol, g):
    pos = adc[pol==1].mean(axis=0); neg = adc[pol==-1].mean(axis=0)
    # Compare the two polarities over their common interior for every candidate delay.
    # Omitting eight grid points at either end keeps the domain fixed during calibration.
    target = g.target[8:-8]

    def compare(delay):
        p = linear_regrid(g.native_kx(1,delay), _demodulated(pos,g,delay), target)
        n = linear_regrid(g.native_kx(-1,delay), _demodulated(neg,g,delay), target)
        cross = np.vdot(n,p)
        return abs(cross)/np.sqrt(np.vdot(p,p).real*np.vdot(n,n).real), np.angle(cross)

    trials = np.linspace(-8,8,33)
    j = int(np.argmax([compare(t)[0] for t in trials]))
    lo, hi = trials[max(0,j-1)], trials[min(len(trials)-1,j+1)]
    opt = minimize_scalar(lambda t: -compare(t)[0], bounds=(lo,hi), method='bounded')
    coherence, phase = compare(opt.x)
    return NavFit(float(opt.x),float(phase),float(coherence))


def fit_b0_navigators(d,g):
    """The b=1000 nav is present in the excerpt and never enters this fit."""
    return _fit_nav(d['nav_adc'][0],d['nav_pol'][0],g)


def native_correct(adc, polarity, g, fit):
    """Return corrected complex samples in ADC order and their delayed physical kx."""
    native = _demodulated(adc,g,fit.delay_us) * np.exp(-.5j*polarity*fit.phase_rad)
    return native, g.native_kx(polarity,fit.delay_us)


def _transform(a, inverse, axis=0):
    op = fft.ifft if inverse else fft.fft
    return fft.fftshift(op(fft.ifftshift(a,axes=axis),axis=axis,norm='ortho'), axes=axis)


def _grid_train(adc, pol, ky, g, fit, rows, *, ramp=True):
    by_ky = np.zeros((len(g.target),128,adc.shape[-1]),dtype=np.complex64)
    for p in (1,-1):
        mask = pol==p
        native, k = native_correct(adc[mask],p,g,fit)
        if not ramp:
            # Omission control: keep the fitted timing displacement and endpoints,
            # but assume that nominal ADC positions are equally spaced in kx.
            nominal = g.native_kx(p)
            uniform = np.linspace(nominal[0], nominal[-1], len(nominal))
            k = uniform + (k - nominal)
        by_ky[:,ky[mask]] = np.moveaxis(linear_regrid(k,native,g.target),0,1)
    # Crop oversampling in readout image space; return the corresponding Cartesian k-space.
    lo=(len(g.target)-128)//2
    cropped = _transform(by_ky[:,rows],True)[lo:lo+128]
    return _transform(cropped,False)


def correct_and_regrid(d,g,fit, *, ghost=True, ramp=True):
    """Grid images and their separate calibration train with matched readout processing."""
    if not ghost:
        fit = NavFit(0., 0., np.nan)
    images = [_grid_train(adc,pol,ky,g,fit,slice(None),ramp=ramp)
              for adc,pol,ky in zip(d['im_adc'],d['im_pol'],d['im_ky'])]
    # The separate calibration train has its own reference echoes and readout history.
    acs_fit = _fit_nav(d['acs_nav_adc'],d['acs_nav_pol'],g) if ghost else fit
    acs = _grid_train(d['acs_adc'],d['acs_pol'],d['acs_ky'],g,acs_fit,slice(32,96),ramp=ramp)
    return images, acs


def _features(k, target_ky):
    # Six neighboring acquired vectors: kx offsets -1,0,+1 on both sides in ky.
    return np.concatenate([np.roll(k,dx,axis=0)[:,(target_ky+dy)%k.shape[1]]
                           for dy in (-1,1) for dx in (-1,0,1)],axis=2)


def fit_grappa_weights(acs):
    """Train a regularized GRAPPA kernel on the contiguous multicoil calibration band."""
    # Interior odd calibration targets each have measured even lines above and below.
    targets = np.arange(1,acs.shape[1]-1,2)
    design = _features(acs,targets).reshape(-1,6*acs.shape[2])
    targets_acs = acs[:,targets].reshape(-1,acs.shape[2])
    gram=design.conj().T@design
    ridge=1.e-3*np.trace(gram).real/len(gram)
    return linalg.solve(gram+ridge*np.eye(len(gram),dtype=gram.dtype),
                        design.conj().T@targets_acs,assume_a='pos')


def grappa_fill(cartesian, weights, targets):
    """Return complex coil data with predictions only at the specified ky indices."""
    filled = cartesian.copy()
    filled[:, targets] = _features(cartesian, targets) @ weights
    return filled


def reconstruct_r2(cart,acs):
    """Fill the full-span R=2 acquisition, inverse Fourier transform and combine coils."""
    from bart_io import bart

    weights = fit_grappa_weights(acs)
    images=[]
    for measured in cart:
        missing = np.arange(1, measured.shape[1], 2)
        k = grappa_fill(measured, weights, missing)
        # BART dims 0,1 are x,y; mask 8 combines the receive channels in dim 3.
        coil_images = bart(['fft','-iu','3'],k[:,:,None,:])
        images.append(np.squeeze(bart(['rss','8'],coil_images)).real)
    return images


def show_trajectory(g, fit, native, kx, cart_line):
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(1,3,figsize=(12.4,3.3),layout='constrained')
    blue, brown = '#21658a', '#ad5731'
    t = np.linspace(0, g.up+g.flat+g.down, 501)
    unit = lambda z: np.clip(np.minimum(z/g.up,(g.up+g.flat+g.down-z)/g.down),0,1)
    # plateau dk/dt in cycles/m per microsecond; proton gamma-bar in cycles/s/T
    gmax = g.scale*1.e9/42.57747892e6
    ax[0].plot(t, gmax*unit(t), color=blue, label='Trapezoid')
    ax[0].plot(g.t[::8],gmax*unit(g.t[::8]),'.',color=brown,label='Every 8th ADC')
    ax[0].set(title='Header-derived readout gradient',xlabel='Time (µs)',ylabel='$G_x$ (mT/m)')
    ax[0].legend(fontsize=8,frameon=False,loc='lower center')
    for pol,color,label in [(1,blue,'Forward'),(-1,brown,'Reversed')]:
        line = g.native_kx(pol,fit.delay_us)
        ax[1].plot(g.t,line,color=color,label=label)
        ax[1].plot(g.t[::12],line[::12],'.',color=color,ms=4)
    ax[1].set(title='ADC trajectory after delay correction',xlabel='Time (µs)',ylabel='$k_x$ (cycles/m)')
    ax[1].legend(fontsize=8,frameon=False)
    coil = np.argmax(np.linalg.norm(native,axis=0))
    points = np.arange(5,17)
    lo, hi = kx[points].min(), kx[points].max()
    keep = (g.target>=lo) & (g.target<=hi)
    ax[2].plot(kx[points],native[points,coil].real,'o-',color=blue,ms=4,label='Native ADC')
    ax[2].plot(g.target[keep],cart_line[keep,coil].real,'x',color=brown,ms=7,mew=1.5,label='Uniform grid')
    ax[2].set(title='Measured b=0 echo on the ramp',xlabel='$k_x$ (cycles/m)',ylabel='Real signal (a.u.)')
    ax[2].ticklabel_format(axis='y',style='sci',scilimits=(-2,2));ax[2].legend(fontsize=8,frameon=False)
    plt.show()


def show_brain_images(images):
    import matplotlib.pyplot as plt

    b0,dwi = images
    common=np.percentile(b0,98); dw_limit=np.percentile(dwi,99)
    fig,axes=plt.subplots(1,3,figsize=(10.3,3.4),layout='constrained')
    panels=[(b0,common,'b=0 image · shared window'),(dwi,common,'b=1000 · shared window'),
            (dwi,dw_limit,'b=1000 · own window')]
    for ax,(im,vmax,title) in zip(axes,panels):
        ax.imshow(im.T,origin='lower',cmap='gray',vmin=0,vmax=vmax,interpolation='nearest')
        ax.set(xlabel='Readout pixel',title=title,xticks=[0,64,127],yticks=[0,64,127])
    axes[0].set_ylabel('Phase-encode pixel')
    plt.show()
