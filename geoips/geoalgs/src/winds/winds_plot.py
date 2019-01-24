#!/bin/env python
import os

# Installed Libraries
import logging
from matplotlib import cm, colors
import numpy as np
from scipy.interpolate import griddata
import re

# GeoIPS Libraries
from geoips.utils.normalize import normalize
from geoips.utils.gencolormap import get_cmap
from .winds_utils import downsample_winds, ms_to_kts

log = logging.getLogger(__name__)


def set_winds_plotting_params(gi, speed=None, pressure=None, altitude=None, platform=None, source=None,
        platform_display=None, source_display=None, prodname=None, bgname=None, start_dt=None, end_dt=None,
        listedColormapVals=None, ticksVals=None):

    # NOTE this actually changes the attributes on the actual datafile, since it is not a copy.
    # This can have unintended consequences (like subsequent sectors not running, because source/platform
    # no longer matches what sectorfile is expecting). Use carefully
    gi.set_geoimg_attrs(platform, source, prodname, platform_display, source_display, bgname, start_dt=start_dt, end_dt=end_dt)
    cbtitle = None

    if pressure is not None or altitude is not None:
        from matplotlib.colors import ListedColormap, BoundaryNorm

        #cmap.set_over('0.25') 
        #cmap.set_under('0.75') 

        #      5m = 1012.65 mb
        #    500m =  954.61 mb
        #   1000m =  898.75 mb
        #   2000m =  794.95 mb
        #   4000m =  616.40 mb
        #   7000m =  410.61 mb
        #  10000m =  264.36 mb
        #  16000m =   96.32 mb
        #  20000m =   43.28 mb
        #  40000m =    0.00 mb
        #  44330m =    0.00 mb
        #  44331m =   ERROR
        # Using standard atmosphere, for reference.
        # These will actually be calculated using model heights

        minval = 0
        if pressure is not None:
            if ticksVals is not None:
                cmap = ListedColormap(listedColormapVals)
                ticks = ticksVals
                minval = ticks[0]
                maxval = ticks[-1]
            else:
                maxval = 1013
                if pressure.max() > maxval:
                    maxval = int(pressure.max())
                if pressure.min() < minval:
                    minval = int(pressure.min())
                ticks = [minval,400,800,maxval]
                cmap = ListedColormap(['green','blue','tan'])
            cbtitle = 'Atmospheric Pressure at Cloud Top, mb'
        elif altitude is not None:
            if ticksVals is not None:
                cmap = ListedColormap(listedColormapVals)
                ticks = ticksVals
                minval = ticks[0]
                maxval = ticks[-1]
            else:
                maxval = 44
                if altitude.max() > maxval:
                    maxval = int(altitude.max())
                if altitude.min() < minval:
                    minval = int(altitude.min())
                cmap = ListedColormap(['tan','salmon','blue','cyan','green','limegreen','chartreuse','lime','magenta'])
                ticks = [minval,1,2,4,7,10,16,20,40,maxval]
            cbtitle = 'Cloud Top Altitude, km'

        bounds = [minval-1] + ticks + [maxval+1]

        norm = BoundaryNorm(ticks, cmap.N)
        spacing = 'uniform'
        ticklabels = None

        gi.set_colorbars(cmap, ticks, ticklabels=ticklabels, title=cbtitle, bounds=None, norm=norm, spacing=spacing)

    elif speed is not None:
        from matplotlib.colors import ListedColormap, BoundaryNorm

        cmap = ListedColormap(['tan','blue','cyan','green','yellow','red','magenta'])
        #cmap.set_over('0.25') 
        #cmap.set_under('0.75') 

        maxval = speed.max()
        if maxval > 100:
            maxval = speed.max()
        else:
            maxval = 200

        ticks = [0,5,25,35,50,64,100,maxval]
        bounds = [-1,0,5, 25, 35, 50, 64, 100, maxval, maxval+1]
        norm = BoundaryNorm(ticks, cmap.N)
        spacing = 'uniform'
        ticklabels = None
        cbtitle = 'Wind speed, knots'

        gi.set_colorbars(cmap, ticks, ticklabels=ticklabels, title=cbtitle, bounds=None, norm=norm, spacing=spacing)

    else:
        gi._colorbars = []

    # Figure and axes
    gi._figure, gi._axes = gi._create_fig_and_ax()


def get_pressure_levels(pres, arrays, pressure_cutoffs=[0,400,800,1014]):
    levArrays = []
    for arrInd in range(len(arrays)):
        currArr = arrays[arrInd]
        levArrays += [[]]
        for presCutoffInd in range(len(pressure_cutoffs)-1):
            pres1 = pressure_cutoffs[presCutoffInd]
            pres2 = pressure_cutoffs[presCutoffInd+1]
            inds = np.argwhere((pres >= pres1) & (pres <= pres2))
            levArrays[arrInd] += [currArr[inds]]  

    return levArrays

def winds_plot(gi, imgkey=None):


    df = gi.image[imgkey]['datafile']
    ds = df.datasets[imgkey]

    bgname = 'None' 
    prodname = imgkey
    day_percent = None
    if 'BACKGROUND' in gi.image[imgkey]:
        bgfile = gi.image[imgkey]['BACKGROUND']
        bgvarname = df.metadata['ds'][imgkey]['alg_channel']
        bgvar = np.flipud(bgfile.variables[bgvarname])
        lats = bgfile.geolocation_variables['Latitude']
        lons = bgfile.geolocation_variables['Longitude']
        sunzen = bgfile.geolocation_variables['SunZenith']
        from .motion_config import motion_config
        from geoips.geoalgs.lib.dataEnhancements import enhanceDataArrays
        if bgvar.name not in motion_config(bgfile.source_name).keys():
            log.warning('Variable %s not defined in motion_config for %s, can not find background, not plotting'%
				(bgvar.name, bgfile.source_name))
            return
        config = motion_config(bgfile.source_name)[bgvar.name]
        bgcmap = 'Greys'
        if 'plot_params' in config.keys() \
            and 'EnhImage' in config['plot_params'].keys() \
            and 'cmap' in config['plot_params']['EnhImage'].keys():
            bgcmap = config['plot_params']['EnhImage']['cmap']

        bgvar, blah, blah2 = enhanceDataArrays(bgvar, config, sunzen1=sunzen)

        chanstr = re.sub(r"^B","Channel ",bgvarname).replace('BT',' BT').replace('Ref',' Reflectance')
        if bgvar.wavelength:
            bgname = '%s - %s, %s um'%(bgvar.platform_name, chanstr, bgvar.wavelength)
        else:
            bgname = '%s - %s'%(bgvar.platform_name, chanstr)
        if np.ma.count(bgvar):
            try:
                day_percent = (1.0 * np.ma.count(bgvar[ds.day_inds]) / np.ma.count(bgvar)) * 100
            except KeyError:
                pass

    if gi.datafile.dataprovider is not None:
        prodname = prodname+', '+gi.datafile.dataprovider
    if day_percent is not None:
        prodname = '%s Product: %d'%(prodname, day_percent) + '% day'
    prodname = prodname.replace('_',' ')

    log.info('Setting up fig and ax for dataset: %s with bgname: %s'%(prodname, bgname))

    new_platform = gi.datafile.metadata['top']['alg_platform']
    new_source = gi.datafile.metadata['top']['alg_source']

    log.info('Plotting dataset: %s'%(imgkey))

    resolution = min(gi.sector.area_info.proj4_pixel_width, gi.sector.area_info.proj4_pixel_height)
    qi = ds.variables['qis']
    good_inds = np.ma.where(qi>0.2)
    # Plot knots, store in text file as m/s
    direction_deg = ds.variables['direction_deg'][good_inds]
    speed_kts = ms_to_kts(ds.variables['speed_ms'][good_inds])
    u_kts = -1.0*speed_kts * np.sin(np.radians(direction_deg))
    v_kts = -1.0*speed_kts * np.cos(np.radians(direction_deg))
    pres_mb = ds.variables['pres_mb'][good_inds]
    lats = ds.variables['lats'][good_inds]
    lons = ds.variables['lons'][good_inds]
    [lons, lats, u_kts, v_kts, speed_kts, direction_deg, pres_mb] = downsample_winds(resolution, thinvalue=10,
                           arrs=[lons, lats, u_kts, v_kts, speed_kts, direction_deg, pres_mb])

    if 'allpress' in imgkey:
        colorLevs = ['cyan','yellow','green'] 
        pressureLevs = [400,600,800,950] 
        [lats,lons,u_kts,v_kts] = get_pressure_levels(pres_mb, [lats,lons,u_kts,v_kts], pressureLevs)


    # Note - if we set this to platform_display and source_display, the 
    # filenames will not reflect the actual satellite/sensor (winds/winds).
    # But when it is set to platform/source, it actually changes the platform
    # and source in the datafile, which breaks all subsequent sectors.
    # So using set_winds_plotting_params to change source/platform
    # FORCES a single sector. I'll have to look into whether there is
    # an intelligent way to handle this. For now. One sector...
    if speed_kts.shape[0] == 0:
        log.warning('No valid winds, returning without attempting to plot')
        return 
    if 'allpress' in imgkey:
        set_winds_plotting_params(gi, speed=None, pressure=pres_mb, altitude=None, 
            #platform_display=new_platform, source_display=new_source, 
            platform=new_platform, source=new_source, 
            prodname=prodname, bgname=bgname, listedColormapVals=colorLevs,
            ticksVals = pressureLevs)
    else:
        set_winds_plotting_params(gi, speed_kts, None, None, 
            #platform_display=new_platform, source_display=new_source, 
            platform=new_platform, source=new_source, 
            prodname=prodname, bgname=bgname)

    if 'BACKGROUND' in gi.image[imgkey]:
        log.info('Plotting background image %s'%(bgname))
        gi.basemap.imshow(bgvar,ax=gi.axes,cmap=get_cmap(bgcmap))


    '''
    NOTE there appears to be an error in basemap - I had to add a try except to allow 
    for different outputs from np.where
    4778                 thresh = 360.-londiff_sort[-2] if nlons > 2 else 360.0 - londiff_sort[-1]
    ***4779                 try:
    ***4780                     itemindex = len(lonsin)-np.where(londiff>=thresh)[0][0]
    ***4781                 except IndexError:
    ***4782                     itemindex = len(lonsin)-np.where(londiff>=thresh)[0]
    4783             else:
    4784                 itemindex = 0
    4785
    4786             if fix_wrap_around and itemindex:
    4787                 # check to see if cyclic (wraparound) point included
    4788                 # if so, remove it.
    4789                 if np.abs(lonsin[0]-lonsin[-1]) < 1.e-4:
    4790                     hascyclic = True
    4791                     lonsin_save = lonsin.copy()
    4792                     lonsin = lonsin[1:]
    /satops/geoips_externals_nrl-2.7/built/anaconda2/lib/python2.7/site-packages/mpl_toolkits/basemap/__init__.py
    '''


    if 'allpressure' in imgkey:
        log.info('Plotting all barbs with colors {} at pressure levels {}'.format(colorLevs, pressureLevs))

        for (ulev,vlev,latlev,lonlev,colorlev) in zip(u_kts,v_kts,lats,lons, colorLevs):
            if ulev.shape[0] == 0:
                log.info('Not plotting color {}, no winds'.format(colorlev))
                continue
            log.info('Plotting color {}'.format(colorlev))

            gi.basemap.barbs(lonlev.data,latlev.data,
                        ulev,vlev,
                        color=colorlev,
                        ax=gi.axes,
                        #sizes=dict(height=0.8, spacing=0.3),
                        sizes=dict(height=0.7, spacing=0.5),
                        linewidth=0.5,
                        length=3,
                        #length=5,
                        latlon=True)
    else:
        log.info('Plotting single level barbs with colorbars %s'%(gi.colorbars))

        gi.basemap.barbs(lons.data,lats.data,
                        u_kts,v_kts,speed_kts,
                        ax=gi.axes,
                        cmap=gi.colorbars[0].cmap,
                        #sizes=dict(height=0.8, spacing=0.3),
                        sizes=dict(height=1, spacing=0.5),
                        norm=gi.colorbars[0].norm,
                        linewidth=0.5,
                        length=5,
                        #length=5,
                        latlon=True)


    if gi.is_final:
        gi.finalize()
