"""
pyProm: Copyright 2016

This software is distributed under a license that is described in
the LICENSE file that accompanies it.

This file contains a class for walking from Saddles to Summits.

"""
import logging
from collections import defaultdict
from lib.locations.gridpoint import GridPoint
from lib.locations.summit import Summit
from lib.containers.linker import Linker


class Walk(object):
    def __init__(self, summits, saddles, datamap):

        self.logger = logging.getLogger('pyProm.{}'.format(__name__))
        self.logger.info("Initiating Walk")
        self.summits = summits
        self.saddles = saddles
        self.datamap = datamap
        self.linkers = list()

        self.logger.info("Create Fast Lookup Hash for Summit Objects.")
        self.summitHash = self._to_hash(self.summits)

    def _to_hash(self, container):
        """
        :param container:
        :return:
        """
        nesteddict = lambda: defaultdict(nesteddict)
        hash = nesteddict()
        for point in container.points:
            if point.multiPoint:
                for mp in point.multiPoint.points:
                    hash[mp.x][mp.y] = point
            else:
                hash[self.datamap.latitude_to_x(
                        point.latitude)][self.datamap.longitude_to_y(
                            point.longitude)]\
                    = point
        return hash

    def run(self):
        # iterate through saddles
        for saddle in self.saddles:
            self.walk(saddle)

    def walk(self, saddle):
        # iterate through high Shores
        self.linkers = list()
        for highEdge in saddle.highShores:
            # Sort High Shores from high to low
            highEdge.points.sort(key=lambda x: x.elevation, reverse=True)
            lookback = 1
            point = highEdge.points[0]
            path = list([point])
            exemptHash = defaultdict(list)

            while True:
                ####
                if len(path) > 5000:
                    self.logger.info("BORK! stuck at {}".format(point))
                    return path
                ####
                point = self._climb_up(point, exemptHash)
                if isinstance(point, Summit):
                    link = Linker(point, saddle, path)
                    self.linkers.append(link)
                    saddle.summits.append(link)
                    point.saddles.append(link)
                    break
                if point:
                    exemptHash[point.x].append(point.y)
                    lookback = 1
                    path.append(point)
                else:
                    lookback += 1
                    point = path[-lookback]

        if len(set(saddle.summits)) == 1:
            saddle.disqualified = True
        return self.linkers

    def _climb_up(self, point, exemptHash):

        if self.summitHash[point.x][point.y]:
            return self.summitHash[point.x][point.y]

        lastElevation = point.elevation
        currentHigh = lastElevation
        candidates = list()

        neighbors = self.datamap.iterateDiagonal(point.x, point.y)
        for x, y, elevation in neighbors:
            if y in exemptHash[x]:
                continue
            if elevation > currentHigh and elevation > lastElevation:
                currentHigh = elevation
                candidates = list()
                candidates.append(GridPoint(x, y, elevation))
            if elevation == currentHigh:
                candidates.append(GridPoint(x, y, elevation))
        if candidates:
            winner = candidates[0]
        else:
            winner = None
        return winner

    def mark_redundant_linkers(self):
        for saddle in self.saddles:
            pass
