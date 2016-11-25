#!/usr/bin/env python3
import os, sys
import matplotlib.pyplot as plt
import tomht.radarSimulator as sim
import numpy as np
import xml.etree.ElementTree as ET
from simSettings import *
import ast

def openRes(filename):
	try:
		f = open(filename)
		trackList = []
		for track in f:
			posStringArray = "".join(track.split()).strip(" ( ) ").split("),(")
			trackArray = []
			for pos in posStringArray:
				trackArray.append( np.array( pos.split(","), dtype = float) )
			trackList.append(np.asarray(trackArray))
		return np.asarray(trackList)
	except:
		return

def openGroundTruth(filename):
	(initialTargets, simList) = sim.importFromFile(filename)
	nTargets = len(initialTargets)
	nTimestep= len(simList)
	targetTracks = np.zeros((nTargets,nTimestep+1,2))
	for target in range(nTargets):
		for timestep in range(nTimestep+1):
			if timestep == 0:
				targetTracks[target,timestep,:] = initialTargets[target].state[0:2]
			else:
				targetTracks[target,timestep,:] = simList[timestep-1][target].state[0:2]
	return np.asarray(targetTracks)

def compareResults():
	root = ET.Element("simulations")
	for fileString in croppedFiles:
		filePath = os.path.join(loadLocation,os.path.splitext(fileString)[0],fileString)
		doc = ET.SubElement(root,"file", name = os.path.basename(fileString))
		trueTracks = openGroundTruth(filePath)
		trueTrackLength = len(trueTracks[0])
		nTracksTrue = trueTracks.shape[0]
		for solver in solvers:
			solv = ET.SubElement(doc, "Solver", name = solver)
			for P_d in PdList:
				prob = ET.SubElement(solv, "P_d", value = str(P_d))
				for N in NList:
					num = ET.SubElement(prob, "N", value = str(N))
					for lambda_phi in lambdaPhiList:
						nTracks = 0
						nLostTracks = 0
						print('{:45s}'.format(os.path.splitext(fileString)[0]),'{:6s}'.format(solver),"P_d =",P_d,"N =",N,"lPhi =",'{:5.0e}'.format(lambda_phi), end = "\n")
						savefilePath = (os.path.join(loadLocation,os.path.splitext(fileString)[0],"results",os.path.splitext(fileString)[0])
											+"["
											+solver.upper()
											+",Pd="+str(P_d)
											+",N="+str(N)
											+",lPhi="+'{:7.5f}'.format(lambda_phi)
											+"]"
											+".xml")
						try:
							simulations = ET.parse(savefilePath).getroot()
						except FileNotFoundError:
							print("x"*nMonteCarlo)
							continue

						iList = [int(sim.get("i")) for sim in simulations.findall("Simulation")]
						totalSimTime = sum([float(sim.get("totalSimTime")) for sim in simulations.findall("Simulation")])
						iList.sort() 
						missingSimulationIndecies = set(range(nMonteCarlo)).difference(set(iList))

						nSimulations = int(simulations.attrib.get('nMonteCarlo'))
						for simulation in simulations:
							parsedTracks = ast.literal_eval(simulation.text)
							estimatedTracks = np.array(parsedTracks)
							if nTracksTrue != len(parsedTracks):
								print("/", end ="", flush = True)
								continue
							
							if any(len(track) != trueTrackLength for track in parsedTracks):
								print("/", end ="", flush = True)
								continue

							if estimatedTracks is None:
								print("x",end = "")
								continue

							if trueTracks.shape != estimatedTracks.shape:
								# os.remove(savefile)
								print("o",end = "")
								continue
							lostTracks = np.linalg.norm(trueTracks-estimatedTracks,2,2) > threshold
							lostTracksTime = [np.flatnonzero(lostTrack).tolist() for lostTrack in lostTracks]
							permanentLostTracks = []
							for lostTrackTime in lostTracksTime:
								if len(lostTrackTime):
									permanentLostTracks.append(lostTrackTime[-1] == trueTrackLength-1)
							nLostTracks += sum(permanentLostTracks)
							nTracks += len(estimatedTracks)
							print(".", end = "")
						if nTracks != 0:
							print("\t",'{:3.0f}'.format(nLostTracks),"/",'{:3.0f}'.format(nTracks),"=>",'{:4.1f}'.format((nLostTracks/nTracks)*100),"%")
							lambdaPhi = ET.SubElement(num,"lambda_phi", value = '{:5.0e}'.format(lambda_phi))
							ET.SubElement(lambdaPhi,"nTracks").text 	= repr(nTracks)
							ET.SubElement(lambdaPhi,"nLostTracks").text = repr(nLostTracks)
							ET.SubElement(lambdaPhi,"totalTime").text 	= repr(totalSimTime)
							ET.SubElement(lambdaPhi,"runtimeLog").text 	= simulation.get("runtimeLog")
							ET.SubElement(lambdaPhi,"nSimulations").text= repr(nSimulations)
							# ET.SubElement(lambdaPhi,"covConsistence").text = simulation.get("covConsistence")
						else:
							print()
	tree = ET.ElementTree(root)
	tree.write("compareResult.xml")

if __name__ == '__main__':
	os.chdir( os.path.dirname(os.path.abspath(__file__)) )
	compareResults()