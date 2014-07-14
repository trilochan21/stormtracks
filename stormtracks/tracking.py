from collections import OrderedDict

import numpy as np

from utils.utils import dist, pairwise

class VortMaxTrack(object):
    '''
    Stores a collection of VortMax objects in a list and adds them to a 
    dict that is accessible through a date for easy access.
    '''
    def __init__(self, start_vortmax):
        if len(start_vortmax.prev_vortmax):
            raise Exception('start vortmax must have no previous vortmaxes')

        self.start_vortmax = start_vortmax
        self.vortmaxes = []
        self.vortmax_by_date = OrderedDict()

        self._build_track()

    def _build_track(self):
        self.vortmaxes.append(self.start_vortmax)
        if len(self.start_vortmax.next_vortmax):
            vortmax = self.start_vortmax.next_vortmax[0]
            self.vortmax_by_date[vortmax.date] = vortmax

            while len(vortmax.next_vortmax) != 0:
                self.vortmaxes.append(vortmax)
                vortmax = vortmax.next_vortmax[0]
                self.vortmax_by_date[vortmax.date] = vortmax
	
	self.lons = np.zeros(len(self.vortmaxes))
	self.lats = np.zeros(len(self.vortmaxes))
	self.dates = np.zeros(len(self.vortmaxes)).astype(object)
	for i, vortmax in enumerate(self.vortmaxes):
	    self.lons[i], self.lats[i] = vortmax.pos[0], vortmax.pos[1]
	    self.dates[i] = vortmax.date


class VortMax(object):
    '''
    Holds key info (date, position, vorticity value) about a vorticity
    maximum.

    To serialize this class (or any that contain objects of this class)
    you must make sure next_vortmax/prev_vortmax are None.
    '''
    def __init__(self, date, pos, vort):
        # TODO: should probably hold ensemble member too.
        self.date = date
        self.pos  = pos
        self.vort  = vort
        self.next_vortmax = []
        self.prev_vortmax = []
        self.secondary_vortmax = []

    def add_next(self, vortmax):
        self.next_vortmax.append(vortmax)
        vortmax.prev_vortmax.append(self)


class VortmaxNearestNeighbourTracker(object):
    def __init__(self, gdata):
        self.gdata = gdata

    def _construct_vortmax_tracks_by_date(self):
        self.vort_tracks_by_date = OrderedDict()
        # Find all start vortmaxes (those that have no previous vortmaxes)
        # and use these to generate a track.
        for vortmaxes in self.vortmax_time_series.values():
            for vortmax in vortmaxes:
                if len(vortmax.prev_vortmax) == 0:
                    vortmax_track = VortMaxTrack(vortmax)
                    for date in vortmax_track.vortmax_by_date.keys():
                        if not date in self.vort_tracks_by_date:
                            self.vort_tracks_by_date[date] = []
                        self.vort_tracks_by_date[date].append(vortmax_track)

                # Allows vort_tracks_by_date to be serialized.
                vortmax.next_vortmax = None
                vortmax.prev_vortmax = None

    def track_vort_maxima(self, start_date, end_date, use_upscaled=False):
        if start_date < self.gdata.dates[0]:
            raise Exception('Start date is out of date range, try setting the year appropriately')
        elif end_date > self.gdata.dates[-1]:
            raise Exception('End date is out of date range, try setting the year appropriately')

        index = np.where(self.gdata.dates == start_date)[0][0]
        end_index = np.where(self.gdata.dates == end_date)[0][0]

        self.vortmax_time_series = OrderedDict()

        dist_cutoff = 10
        vort_cutoff = 5e-5
        while index <= end_index:
            date = self.gdata.dates[index]
            self.gdata.set_date(date)

            vortmaxes = []

	    if use_upscaled:
		vmaxs = self.gdata.c20data.up_vmaxs
	    else:
		vmaxs = self.gdata.c20data.vmaxs

            for vmax in vmaxs:
		if (220 < vmax[1][0] < 340 and
		    0 < vmax[1][1] < 60):
		    if vmax[0] > vort_cutoff:
			vortmax = VortMax(date, vmax[1], vmax[0])
			vortmaxes.append(vortmax)

	    secondary_vortmaxes = []
	    for i in range(len(vortmaxes)):
		v1 = vortmaxes[i]
		for j in range(i + 1, len(vortmaxes)):
		    v2 = vortmaxes[j]
		    if dist(v1.pos, v2.pos) < dist_cutoff:
			if v1.vort > v2.vort:
			    v1.secondary_vortmax.append(v2)
			    secondary_vortmaxes.append(v2)
			elif v1.vort <= v2.vort:
			    v2.secondary_vortmax.append(v1)
			    secondary_vortmaxes.append(v1)

	    for v in secondary_vortmaxes:
		if v in vortmaxes:
		    vortmaxes.remove(v)

	    for i, v in enumerate(vortmaxes):
		v.index = i

            self.vortmax_time_series[date] = vortmaxes

            index += 1

        # Loops over 2 lists of vormtaxes
        for vs1, vs2 in pairwise(self.vortmax_time_series.values()):
            for v1 in vs1:
                min_dist = 8
                v2next = None

                # Find the nearest vortmax in the next timestep.
                for v2 in vs2:
                    d = dist(v1.pos, v2.pos)
                    if d < min_dist:
                        min_dist = d
                        v2next = v2

                # Add the nearest vortmax in the next timestep.
                if v2next:
                    v1.add_next(v2next)
                    if len(v1.next_vortmax) != 1:
                        raise Exception('There should only ever be one next_vormax')


        # Some vortmaxes may have more than one previous vortmax.
        # Find these and choose the nearest one as the actual previous.
        for vs in self.vortmax_time_series.values():
            for v in vs:
                if len(v.prev_vortmax) > 1:
                    min_dist = 8
                    vprev = None
                    for pv in v.prev_vortmax:
                        d = dist(pv.pos, v.pos)
                        if d < min_dist:
                            min_dist = d
                            vprev = pv

                    for pv in v.prev_vortmax:
                        if pv != vprev:
                            pv.next_vortmax.remove(v)

                    v.prev_vortmax = [vprev]
        self._construct_vortmax_tracks_by_date()