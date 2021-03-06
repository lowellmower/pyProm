"""
pyProm: Copyright 2016

This software is distributed under a license that is described in
the LICENSE file that accompanies it.
"""

from __future__ import division

import numpy
import logging

from collections import defaultdict
from timeit import default_timer
from datetime import timedelta
from lib.locations.gridpoint import GridPoint
from lib.locations.saddle import Saddle
from lib.locations.summit import Summit
from lib.locations.inverse_edgepoint import InverseEdgePoint
from lib.containers.spot_elevation import SpotElevationContainer
from lib.containers.multipoint import MultiPoint
from lib.containers.inverse_edgepoint import InverseEdgePointContainer
from lib.containers.high_edge import HighEdgeContainer
from lib.containers.gridpoint import GridPointContainer
from lib.util import (coordinateHashToGridPointList,
                      compressRepetetiveChars)


class AnalyzeData(object):
    def __init__(self, datamap):
        """
        :param datamap: `DataMap` object.
        """
        self.logger = logging.getLogger('pyProm.{}'.format(__name__))
        self.datamap = datamap
        self.data = self.datamap.numpy_map
        self.edge = False
        self.max_y = self.datamap.max_y
        self.span_longitude = self.datamap.span_longitude
        self.max_x = self.datamap.max_x
        self.span_latitude = self.datamap.span_latitude
        self.cardinalGrid = dict()
        self.skipAnalysis = defaultdict(list)

    def analyze(self):
        """
        Analyze Routine.
        Looks for :class:`Summit`s, and :class:`Saddle`s
        return: (:class:`SpotElevationContainer`,SpotElevationContainer)
        """
        self.start = default_timer()
        self.lasttime = self.start
        self.logger.info("Initiating Analysis")
        self.summitObjects = SpotElevationContainer([])
        self.saddleObjects = SpotElevationContainer([])
        iterator = numpy.nditer(self.data, flags=['multi_index'])
        index = 0
        # Iterate through numpy grid, and keep track of gridpoint coordinates.
        while not iterator.finished:
            x, y = iterator.multi_index
            self.elevation = float(iterator[0])

            # Quick Progress Meter. Needs refinement,
            index += 1
            if not index % 100000:

                thisTime = default_timer()
                split = round(thisTime - self.lasttime, 2)
                self.lasttime = default_timer()
                rt = self.lasttime - self.start
                pointsPerSec = round(index/rt, 2)
                self.logger.info(
                    "Points per second: {} - {}%"
                    " runtime: {}, split: {}".format(
                        pointsPerSec,
                        round(index/self.data.size * 100, 2),
                        (str(timedelta(seconds=round(rt, 2)))),
                        split
                    ))

            # Check for summit or saddle
            result = self.summit_and_saddle(x, y)
            if result:
                if isinstance(result, Saddle):
                    self.saddleObjects.points.append(result)
                if isinstance(result, Summit):
                    self.summitObjects.points.append(result)
            # Reset variables, and go to next gridpoint.
            self.edge = False
            self.blob = None
            iterator.iternext()
        # Free some memory.
        del(self.skipAnalysis)
        return self.summitObjects, self.saddleObjects

    def analyze_multipoint(self, x, y, ptElevation):
        """
        :param x:
        :param y:
        :param ptElevation: Elevation of Multipoint Blob
        :return: Summit, Saddle, or None
        """
        self.blob = self.equalHeightBlob(x, y, ptElevation)
        highInverseEdge = self.blob.inverseEdgePoints.findHighEdges(
            self.elevation)

        for exemptPoint in self.blob.points:
            self.skipAnalysis[exemptPoint.x] \
                .append(exemptPoint.y)
        if not len(highInverseEdge):
            summit = Summit(self.datamap.x_to_latitude(x),
                            self.datamap.y_to_longitude(y),
                            self.elevation,
                            edge=self.edge,
                            multiPoint=self.blob
                            )
            return summit
        if (len(highInverseEdge) > 1) or\
                (len(highInverseEdge) == 1 and self.edge):
            saddle = Saddle(self.datamap.x_to_latitude(x),
                            self.datamap.y_to_longitude(y),
                            self.elevation,
                            edge=self.edge,
                            multiPoint=self.blob,
                            highShores=highInverseEdge)
            return saddle
        return None

    def summit_and_saddle(self, x, y):
        """
        :param x:
        :param y:
        :return: Summit, Saddle, or None
        """

        # Exempt! bail out!
        if y in self.skipAnalysis[x]:
            return None

        saddleProfile = ["HLHL", "LHLH"]
        summitProfile = "L"

        # Label this as an mapEdge under the following condition
        if x in (self.max_x, 0) or y in (self.max_y, 0):
            self.edge = True

        # Begin the ardous task of analyzing points and multipoints
        neighbor = self.datamap.iterateDiagonal(x, y)
        shoreSet = GridPointContainer([])
        neighborProfile = ""
        for _x, _y, elevation in neighbor:

            # If we have equal neighbors, we need to kick off analysis to
            # a special MultiPoint analysis function.
            if not elevation:
                continue
            if elevation == self.elevation and _y not in \
                    self.skipAnalysis[_x]:
                return self.analyze_multipoint(_x, _y, elevation)
            if elevation > self.elevation:
                neighborProfile += "H"
            if elevation < self.elevation:
                neighborProfile += "L"
            shoreSet.points.append(GridPoint(_x, _y, elevation))

        reducedNeighborProfile = compressRepetetiveChars(neighborProfile)
        if reducedNeighborProfile == summitProfile:
            summit = Summit(self.datamap.x_to_latitude(x),
                            self.datamap.y_to_longitude(y),
                            self.elevation,
                            edge=self.edge)
            return summit

        elif any(x in reducedNeighborProfile for x in saddleProfile):
            shores = HighEdgeContainer(shoreSet, self.elevation)
            saddle = Saddle(self.datamap.x_to_latitude(x),
                            self.datamap.y_to_longitude(y),
                            self.elevation,
                            edge=self.edge,
                            highShores=[GridPointContainer(x)
                                        for x in shores.highPoints])
            return saddle
        return None

    def equalHeightBlob(self, x, y, elevation):
        """
        This function generates a list of coordinates that involve equal height
        :param x: x coordinate
        :param y: y coordinate
        :param elevation: elevation
        :return: Multipoint Object containing all x,y coordinates and elevation
        """

        masterGridPoint = GridPoint(x, y, elevation)
        equalHeightHash = defaultdict(list)
        equalHeightHash[x].append(y)
        nesteddict = lambda: defaultdict(nesteddict)
        inverseEdgeHash = nesteddict()  # InverseEdgepoint (shore).
        toBeAnalyzed = [masterGridPoint]

        # Loop until pool of equalHeight neighbors has been exhausted.
        while toBeAnalyzed:
            gridPoint = toBeAnalyzed.pop()
            neighbors = self.datamap.iterateDiagonal(gridPoint.x, gridPoint.y)
            # Determine if edge or not.
            if gridPoint.x in (self.max_x, 0) or gridPoint.y in \
                    (self.max_y, 0):
                self.edge = True
            for _x, _y, elevation in neighbors:
                if elevation == masterGridPoint.elevation and\
                                _y not in equalHeightHash[_x]:
                    branch = GridPoint(_x, _y, elevation)
                    equalHeightHash[_x].append(_y)
                    toBeAnalyzed.append(branch)
                elif elevation != masterGridPoint.elevation:
                    if not inverseEdgeHash[_x][_y]:
                        inverseEdgeHash[_x][_y] = \
                            InverseEdgePoint(_x, _y, elevation)

        return MultiPoint(coordinateHashToGridPointList(equalHeightHash),
                          masterGridPoint.elevation, self.datamap,
                          inverseEdgePoints=InverseEdgePointContainer(
                              inverseEdgePointIndex=inverseEdgeHash,
                              datamap=self.datamap, mapEdge=self.edge)
                          )
