from __future__ import print_function
import matplotlib.pyplot as plt
import numpy as np
import logging

# ----------------------------------------------------------------------------
# Instantiate logging object
# ----------------------------------------------------------------------------
log = logging.getLogger(__name__)
log.setLevel(logging.DEBUG)
log.debug("Loaded helpFunctions")
log.info("Loaded helpFunctions")

def _getBestTextPosition(normVelocity, **kwargs):
    DEBUG = kwargs.get('debug', False)
    compassHeading = np.arctan2(normVelocity[0], normVelocity[1]) * 180. / np.pi
    compassHeading = (compassHeading + 360.) % 360.
    assert compassHeading >= 0, str(compassHeading)
    assert compassHeading <= 360, str(compassHeading)
    quadrant = int(2 + (compassHeading - 90) // 90)
    assert quadrant >= 1, str(quadrant)
    assert quadrant <= 4, str(quadrant)
    assert type(quadrant) is int
    if DEBUG: print("Vector {0:} Heading {1:5.1f} Quadrant {2:}".format(normVelocity, compassHeading, quadrant))
    # return horizontal_alignment, vertical_alignment
    if quadrant == 1:
        return 'right', 'top'
    elif quadrant == 2:
        return 'right', 'bottom'
    elif quadrant == 3:
        return 'left', 'bottom'
    elif quadrant == 4:
        return 'left', 'top'
    else:
        print('_getBestTextPosition failed. Returning default')
        return 'center', 'center'


def binomial(n, k):
    return 1 if k == 0 else (0 if n == 0 else binomial(n - 1, k) + binomial(n - 1, k - 1))


def plotVelocityArrowFromNode(nodes, **kwargs):
    def recPlotVelocityArrowFromNode(node, stepsLeft):
        if node.predictedStateMean is not None:
            plotVelocityArrow(node)
        if stepsLeft > 0 and (node.parent is not None):
            recPlotVelocityArrowFromNode(node.parent, stepsLeft - 1)

    for node in nodes:
        recPlotVelocityArrowFromNode(node, kwargs.get("stepsBack", 1))


def plotRadarOutline(ax, centerPosition, radarRange, **kwargs):
    from matplotlib.patches import Ellipse
    if kwargs.get("markCenter", True):
        ax.plot(centerPosition[0], centerPosition[0], "bo")
    circle = Ellipse((centerPosition[0], centerPosition[1]), radarRange * 2, radarRange * 2,
                     edgecolor="black", linestyle="dotted", facecolor="none")
    ax.add_artist(circle)


def plotTrueTrack(ax,simList, **kwargs):
    import copy
    colors = kwargs.get("colors")
    newArgs = copy.copy(kwargs)
    if "colors" in newArgs:
        del newArgs["colors"]

    nScan = len(simList)
    nTargets = len(simList[0])
    stateArray = np.zeros((nScan, nTargets, 4))
    for row, targetList in enumerate(simList):
        stateArray[row, :, :] = np.array([target.cartesianState() for target in targetList])
    for col in range(nTargets):
        ax.plot(stateArray[:, col, 0],
                stateArray[:, col, 1],
                '.',
                alpha=0.7,
                markeredgewidth=0.5,
                color=next(colors) if colors is not None else None,
                markevery=kwargs.get('markevery',1))

    for col, target in enumerate(simList[0]):
        if kwargs.get('markStart', True):
            ax.plot(stateArray[0, col, 0], stateArray[0, col, 1], '.', color='black')
        if kwargs.get('label', False):
            velocity = target.cartesianVelocity()
            normVelocity = (velocity /
                            np.linalg.norm(velocity))
            offsetScale = kwargs.get('offset', 0.0)
            offset = offsetScale * np.array(normVelocity)
            position = stateArray[0,col,0:2] - offset
            (horizontalalignment,
             verticalalignment) = _getBestTextPosition(normVelocity)
            ax.text(position[0],
                    position[1],
                    "T" + str(col),
                    fontsize=kwargs.get('fontsize',10),
                    horizontalalignment=horizontalalignment,
                    verticalalignment=verticalalignment)


def printScanList(scanList):
    for index, measurement in enumerate(scanList):
        print("\tMeasurement ", index, ":\t", end='', sep='')
        measurement.print()


def printHypothesesScore(targetList):
    def recPrint(target, targetIndex):
        if target.trackHypotheses is not None:
            for hyp in target.trackHypotheses:
                recPrint(hyp, targetIndex)

    for targetIndex, target in enumerate(targetList):
        print("\tTarget: ", targetIndex,
              "\tInit", target.initial.position,
              "\tPred", target.predictedPosition(),
              "\tMeas", target.measurement, sep="")

def backtrackMeasurementNumbers(selectedNodes, steps=None):
    def recBacktrackNodeMeasurements(node, measurementBacktrack, stepsLeft=None):
        if node.parent is not None:
            if stepsLeft is None:
                measurementBacktrack.append(node.measurementNumber)
                recBacktrackNodeMeasurements(node.parent, measurementBacktrack)
            elif stepsLeft > 0:
                measurementBacktrack.append(node.measurementNumber)
                recBacktrackNodeMeasurements(
                    node.parent, measurementBacktrack, stepsLeft - 1)

    measurementsBacktracks = []
    for node in selectedNodes:
        measurementNumberBacktrack = []
        recBacktrackNodeMeasurements(node, measurementNumberBacktrack, steps)
        measurementNumberBacktrack.reverse()
        measurementsBacktracks.append(measurementNumberBacktrack)
    return measurementsBacktracks


def backtrackNodePositions(selectedNodes, **kwargs):
    from classDefinitions import Position

    def recBacktrackNodePosition(node, measurementList):
        measurementList.append(Position(node.filteredStateMean[0:2]))
        if node.parent is not None:
            if node.parent.scanNumber != node.scanNumber - 1:
                raise ValueError("Inconsistent scanNumber-ing:",
                                 node.parent.scanNumber, "->", node.scanNumber)
            recBacktrackNodePosition(node.parent, measurementList)

    try:
        trackList = []
        for leafNode in selectedNodes:
            measurementList = []
            recBacktrackNodePosition(leafNode, measurementList)
            measurementList.reverse()
            trackList.append(measurementList)
        return trackList
    except ValueError as e:
        if kwargs.get("debug", False):
            print(e)
        raise


def writeTracksToFile(filename, trackList, time, **kwargs):
    f = open(filename, 'w')
    for targetTrack in trackList:
        s = ""
        for index, position in enumerate(targetTrack):
            s += str(position)
            s += ',' if index != len(targetTrack) - 1 else ''
        s += "\n"
        f.write(s)
    f.close()


def parseSolver(solverString):
    import pulp
    s = solverString.strip().lower()
    if s == "cplex":
        return pulp.CPLEX_CMD(None, 0, 1, 0, [])
    if s == "glpk":
        return pulp.GLPK_CMD(None, 0, 1, 0, [])
    if s == "cbc":
        return pulp.PULP_CBC_CMD()
    if s == "gurobi":
        return pulp.GUROBI_CMD(None, 0, 1, 0, [])
    if s == "pyglpk":
        return pulp.PYGLPK()
    print("Did not find solver", solverString, "\t Using default solver.")
    return None


def solverIsAvailable(solverString):
    s = solverString.strip().lower()
    if s == "cplex":
        return pulp.CPLEX_CMD().available() != False
    if s == "glpk":
        return pulp.GLPK_CMD().available() != False
    if s == "cbc":
        return pulp.PULP_CBC_CMD().available() != False
    if s == "gurobi":
        return pulp.GUROBI_CMD().available() != False
    return False

def writeElementToFile(path, element):
    import xml.etree.ElementTree as ET
    import os
    (head, tail) = os.path.split(path)
    if not os.path.isdir(head):
        os.makedirs(head)
    tree = ET.ElementTree(element)
    tree.write(path)