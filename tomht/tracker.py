"""
========================================================================================
TRACK-ORIENTED-(MULTI-TARGET)-MULTI-HYPOTHESIS-TRACKER (with Kalman Filter and PV-model)
by Erik Liland, Norwegian University of Science and Technology
Trondheim, Norway
Authumn 2016
========================================================================================
"""
import numpy as np
import scipy.sparse
import time
import helpFunctions as hpf
import matplotlib.pyplot as plt
import pulp
from classDefinitions import Position, Velocity
import kalmanFilter as kf

def _nScanPruning(globalHypotheses, N):
	def recPruneNScan(target, targetIndex, targetList, stepsLeft):
		if stepsLeft <= 0:
			if target.parent is not None:
				changed = (targetList[targetIndex] != target)
				targetList[targetIndex] = target
				target.parent._pruneAllHypothesisExeptThis(target)
				return (changed, target.scanNumber)
			else:
				return (False, None)
		elif target.parent is not None:
			return recPruneNScan(target.parent, targetIndex, targetList, stepsLeft-1)
		else:
			return (False, None)
	for targetIndex, target in enumerate(globalHypotheses):
		(changed, scanNumber) = recPruneNScan(target, targetIndex, __targetList__, N)
		if changed:
			__associatedMeasurements__[targetIndex] = __targetList__[targetIndex].getMeasurementSet()

def _pruneSmilarState(target, errorNormLimit):
	# print("Pruning")
	from scipy.special import binom
	nHyp = len(target.trackHypotheses)
	nDelta = int(binom(nHyp,2))
	deltaX = np.zeros([4,nDelta])
	hypotheses = target.trackHypotheses[1:]
	done = set()
	for a in target.trackHypotheses[:-1]:
		for b in hypotheses:
			if a != b:
				targetID = (a.measurementNumber,b.measurementNumber)
				if targetID not in done:
					deltaX[:,len(done)] = (a.filteredStateMean - b.filteredStateMean)
					done.add( targetID )
		hypotheses.pop(0)
	for col in range(nDelta):
		errorNorm = np.linalg.norm(deltaX[:,col])
		# print("Norm",round(errorNorm,3))
		if errorNorm < errorNormLimit:
			# print("Found similar hypotheses")
			if col < nHyp:
				# print("Removing zero hypothesis")
				target.trackHypotheses.pop(0)
				break

def _selectBestHypothesis(target):
	def recSearchBestHypothesis(target,bestScore, bestHypothesis):
		if len(target.trackHypotheses) == 0:
			if target.cummulativeNLLR <= bestScore[0]:
				bestScore[0] = target.cummulativeNLLR
				bestHypothesis[0] = target
		else:
			for hyp in target.trackHypotheses:
				recSearchBestHypothesis(hyp, bestScore, bestHypothesis)
	bestScore = [float('Inf')]
	# bestHypothesis = [None]
	bestHypothesis = np.empty(1,dtype = np.dtype(object))
	recSearchBestHypothesis(target, bestScore, bestHypothesis)
	return bestHypothesis

def _solveOptimumAssociation(cluster):
	nHypInClusterArray = _getHypInCluster(cluster)
	nRealMeasurementsInCluster= len(set.union(*[__associatedMeasurements__[i] for i in cluster]))
	problemSize = nRealMeasurementsInCluster*sum(nHypInClusterArray)
	# print("problemSize", problemSize)
	# if problemSize > problemSizeLimit:
	# 	_nScanPruning(, N-1)
	# 	nHypInClusterArray = _getHypInCluster(cluster)
	# 	nRealMeasurementsInCluster= len(set.union(*[__associatedMeasurements__[i] for i in cluster]))
	# 	print("reduced problemSize:", nRealMeasurementsInCluster*sum(nHypInClusterArray))
	# t0 = time.clock()
	(A1, measurementList) = _createA1(nRealMeasurementsInCluster,sum(nHypInClusterArray), cluster)
	A2 	= _createA2(len(cluster), nHypInClusterArray)
	C 	= _createC(cluster)
	# t1 = time.clock()-t0
	# print("matricesTime\t", round(t1,3))

	selectedHypotheses = _solveBLP(A1,A2, C)
	selectedNodes = _hypotheses2Nodes(selectedHypotheses,cluster)
	# print("Solving optimal association in cluster with targets",cluster,",   \t",
	# sum(nHypInClusterArray)," hypotheses and",nRealMeasurementsInCluster,"real measurements.",sep = " ")
	# print("nHypothesesInCluster",sum(nHypInClusterArray))
	# print("nRealMeasurementsInCluster", nRealMeasurementsInCluster)	
	# print("nTargetsInCluster", len(cluster))
	# print("nHypInClusterArray",nHypInClusterArray)
	# print("c =", c)
	# print("A1", A1, sep = "\n")
	# print("size(A1)", A1.shape, "\t=>\t", nRealMeasurementsInCluster*sum(nHypInClusterArray))
	# print("A2", A2, sep = "\n")
	# print("measurementList",measurementList)
	# print("selectedHypotheses",selectedHypotheses)
	# print("selectedMeasurements",selectedMeasurements)
	#return np.array(selectedMeasurements, dtype = int, ndmin = 2).T
	return np.array(selectedNodes)

def _hypotheses2Nodes(selectedHypotheses, cluster):
	def recDFS(target, selectedHypothesis, nodeList, counter):
		if len(target.trackHypotheses) == 0:
			if counter[0] in selectedHypotheses:
				nodeList.append(target)
			counter[0] += 1
		else:
			for hyp in target.trackHypotheses:
				recDFS(hyp, selectedHypotheses, nodeList, counter)
	nodeList = []
	counter = [0]
	for targetIndex in cluster:
		recDFS(__targetList__[targetIndex], selectedHypotheses, nodeList, counter)
	return nodeList

def _createA1(nRow,nCol,cluster):
	def recActiveMeasurement(target, A1, measurementList,  activeMeasurements, hypothesisIndex):
		if len(target.trackHypotheses) == 0:
			if (target.measurementNumber != 0) and (target.measurementNumber is not None): #we are at a real measurement
				measurement = (target.scanNumber,target.measurementNumber)
				try:
					measurementIndex = measurementList.index(measurement)
				except ValueError:
					measurementList.append(measurement)
					measurementIndex = len(measurementList) -1
				activeMeasurements[measurementIndex] = True
				# print("Measurement list", measurementList)
				# print("Measurement index", measurementIndex)
				# print("HypInd = ", hypothesisIndex[0])
				# print("Active measurement", activeMeasurements)
			A1[activeMeasurements,hypothesisIndex[0]] = True
			hypothesisIndex[0] += 1
			
		else:
			for hyp in target.trackHypotheses:
				activeMeasurementsCpy = activeMeasurements.copy()
				if (hyp.measurementNumber != 0) and (hyp.measurementNumber is not None): 
					measurement = (hyp.scanNumber,hyp.measurementNumber)
					try:
						measurementIndex = measurementList.index(measurement)
					except ValueError:
						measurementList.append(measurement)
						measurementIndex = len(measurementList) -1
					activeMeasurementsCpy[measurementIndex] = True
				recActiveMeasurement(hyp, A1, measurementList, activeMeasurementsCpy, hypothesisIndex)

	A1 	= np.zeros((nRow,nCol), dtype = bool)
	activeMeasurements = np.zeros(nRow, dtype = bool)
	measurementList = []
	hypothesisIndex = [0]
	#TODO: http://stackoverflow.com/questions/15148496/python-passing-an-integer-by-reference
	for targetIndex in cluster:
		recActiveMeasurement(__targetList__[targetIndex],A1,measurementList,activeMeasurements,hypothesisIndex)
	return A1, measurementList

def _createA2(nTargetsInCluster, nHypInClusterArray):
	A2 	= np.zeros((nTargetsInCluster,sum(nHypInClusterArray)), dtype = bool)
	colOffset = 0
	for rowIndex, nHyp in enumerate(nHypInClusterArray):
		for colIndex in range(colOffset, colOffset + nHyp):
			A2[rowIndex,colIndex]=True
		colOffset += nHyp
	return A2

def _createC(cluster):
	def getTargetScore(target, scoreArray):
		if len(target.trackHypotheses) == 0:
			scoreArray.append(target.cummulativeNLLR)
		else:
			for hyp in target.trackHypotheses:
				getTargetScore(hyp, scoreArray)
	scoreArray = []
	for targetIndex in cluster:
		getTargetScore(__targetList__[targetIndex], scoreArray)
	return scoreArray

def _getHypInCluster(cluster):
	def nLeafNodes(target):
		if len(target.trackHypotheses) == 0:
			return 1
		else:
			return sum(nLeafNodes(hyp) for hyp in target.trackHypotheses)
	nHypInClusterArray = np.zeros(len(cluster), dtype = int)
	for i, targetIndex in enumerate(cluster):
		nHypInTarget = nLeafNodes(__targetList__[targetIndex])
		nHypInClusterArray[i] = nHypInTarget
	return nHypInClusterArray

def _solveBLP(A1, A2, f):
	(nMeas, nHyp) = A1.shape
	(nTargets, _) = A2.shape
	prob = pulp.LpProblem("Association problem", pulp.LpMinimize)
	x = pulp.LpVariable.dicts("x", range(nHyp), 0, 1, pulp.LpBinary)
	c = pulp.LpVariable.dicts("c", range(nHyp))
	for i in range(len(f)):
		c[i] = f[i]
	prob += pulp.lpSum(c[i]*x[i] for i in range(nHyp))
	for row in range(nMeas):
		prob += pulp.lpSum([ A1[row,col] * x[col] for col in range(nHyp) ]) <= 1
	for row in range(nTargets):
		prob += pulp.lpSum([ A2[row,col] * x[col] for col in range(nHyp) ]) == 1
	tic = time.clock()
	sol = prob.solve(solver)
	toc = time.clock()-tic
	print("n=",nHyp,"=>",round(toc,3))
	def getSelectedHyp1(p):
		hyp = [int(v.name[2:]) for v in p.variables() if v.varValue ==1]
		hyp.sort()
		return hyp
	def getSelectedHyp2(p):
		hyp = [int(v[0][2:]) for v in p.variablesDict().items() if v[1].varValue==1]
		hyp.sort()
		return hyp
	return getSelectedHyp2(prob)

class Target:
	def __init__(self, **kwargs):
		time 						= kwargs.get("time")
		scanNumber 					= kwargs.get("scanNumber")
		filteredStateMean 			= kwargs.get("state")
		filteredStateCovariance 	= kwargs.get("covariance")
		A 							= kwargs.get("A")	
		Q 							= kwargs.get("Q")
		Gamma 						= kwargs.get("Gamma")	
		C 							= kwargs.get("C")
		R 							= kwargs.get("R")
		sigma 						= kwargs.get("sigma")

		if (time is None) or (scanNumber is None) or (filteredStateMean is None) or (filteredStateCovariance is None):
			raise TypeError("Target() need at least: time, scanNumber, state and covariance")
		#Track parameters
		self.time 	 					= time
		self.scanNumber 				= scanNumber
		self.parent 					= kwargs.get("parent")
		self.measurementNumber 			= kwargs.get("measurementNumber", 0)
		self.measurement 				= kwargs.get("measurement")
		self.cummulativeNLLR 			= kwargs.get("cummulativeNLLR", 0)
		self.trackHypotheses 			= []	
		self.sigma 						= sigma
		self.sigma2 					= np.power(sigma,2)

		#Kalman filter variables
		self.filteredStateMean 			= filteredStateMean
		self.filteredStateCovariance 	= filteredStateCovariance		
		self.predictedStateMean 		= None
		self.predictedStateCovariance 	= None
		self.residualCovariance 		= None

		#State space model
		self.A 							= A
		self.Q 							= Q
		self.Gamma 						= Gamma
		self.C 							= C
		self.R 							= R
	
	def __repr__(self):
		from time import gmtime, strftime
		if self.predictedStateMean is not None:
			np.set_printoptions(precision = 4, suppress = True)
			predStateStr = " \tPredState: " + str(self.predictedStateMean)
		else:
			predStateStr = ""

		if self.measurementNumber is not None:
			measStr = " \tMeasurement(" + str(self.scanNumber) + ":" + str(self.measurementNumber) + ")"
			if self.measurement is not None:
				measStr += ":" + str(self.measurement)
		else:
			measStr = ""

		if self.residualCovariance is not None:
			lambda_, _ = np.linalg.eig(self.residualCovariance)
			gateStr = " \tGate size: ("+'{:5.2f}'.format(np.sqrt(lambda_[0])*2)+","+'{:5.2f}'.format(np.sqrt(lambda_[1])*2)+")"
		else:
			gateStr = ""

		return ("Time: " + strftime("%H:%M:%S", gmtime(self.time))
				+ " \t" + repr(self.getPosition())
				+ " \t" + repr(self.getVelocity()) 
				+ " \tcNLLR:" + '{: 06.4f}'.format(self.cummulativeNLLR)
				+ measStr
				+ predStateStr
				+ gateStr 
				)

	def __str__(self, level=0, hypIndex = 0):
		if (level == 0) and len(self.trackHypotheses) == 0:
			return repr(self)

		ret = ""
		if level != 0:
			ret += "\t" + "\t"*level + "H" + str(hypIndex)+":\t" +repr(self)+"\n"

		for hypIndex, hyp in enumerate(self.trackHypotheses):
			hasNotZeroHyp = (self.trackHypotheses[0].measurementNumber != 0)
			ret += hyp.__str__(level+1, hypIndex + int(hasNotZeroHyp))
		return ret

	def getPosition(self):
		pos = Position(self.filteredStateMean[0:2])
		return pos

	def getVelocity(self):
		return Velocity(self.filteredStateMean[2:4])

	def depth(self, count = 0):
		if len(self.trackHypotheses):
			return self.trackHypotheses[0].depth(count +1)
		return count

	def predictMeasurement(self, Phi, Q, Gamma, C, R):
		self.predictedStateMean, self.predictedStateCovariance = (
				kf.filterPredict(Phi,Gamma.dot(Q.dot(Gamma.T)),self.filteredStateMean,self.filteredStateCovariance))
		self.residualCovariance = C.dot(self.predictedStateCovariance.dot(C.T))+R
	
	def gateAndCreateNewHypotheses(self, measurementList, P_d, 
		lambda_ex, scanNumber, associatedMeasurements):
		time = measurementList.time
		self.trackHypotheses.append(self._generateZeroHypothesis(time, scanNumber, P_d))

		for measurementIndex, measurement in enumerate(measurementList.measurements):
			if self._measurementIsInsideErrorEllipse(measurement, self.sigma2, self.C):
				(_, filtState, filtCov, resCov) = kf.filterCorrect(self.C, self.R, self.predictedStateMean, self.predictedStateCovariance, measurement.toarray() )
				associatedMeasurements.add( (scanNumber, measurementIndex+1) )
				self.trackHypotheses.append(self.clone(
							time = time, 
							scanNumber = scanNumber,
							measurementNumber = measurementIndex+1,
							measurement = measurement,
							state = filtState,
							covariance = filtCov,
							cummulativeNLLR = self.cummulativeNLLR + hpf.nllr(P_d, measurement, np.dot(self.C,self.predictedStateMean), lambda_ex, resCov))

							)

	def clone(self, **kwargs):
		time						=	kwargs.get("time")
		scanNumber					=	kwargs.get("scanNumber")
		filteredStateMean			=	kwargs.get("state")
		filteredStateCovariance		=	kwargs.get("covariance")
		cummulativeNLLR				=	kwargs.get("cummulativeNLLR")
		measurementNumber			=	kwargs.get("measurementNumber")
		measurement					=	kwargs.get("measurement")
		parent						=	kwargs.get("parent",self)
		A							=	kwargs.get("A",		self.A)
		Q							=	kwargs.get("Q",		self.Q)
		Gamma						=	kwargs.get("Gamma",	self.Gamma)
		C							=	kwargs.get("C",		self.C)
		R							=	kwargs.get("R",		self.R)
		sigma						=	kwargs.get("sigma",	self.sigma)

		return Target(
			time 	 					= time,
			scanNumber 					= scanNumber,
			state 						= filteredStateMean,
			covariance 					= filteredStateCovariance,
			parent 						= parent,
			measurementNumber 			= measurementNumber,
			measurement 				= measurement,
			cummulativeNLLR 			= cummulativeNLLR,
			A 							= A,
			Q 							= Q,
			Gamma 						= Gamma,
			C 							= C,
			R 							= R,
			sigma 						= sigma,
			)

	def _measurementIsInsideErrorEllipse(self,measurement, sigma2, C):
		measRes = measurement.toarray()-C.dot(self.predictedStateMean)
		return measRes.T.dot( np.linalg.inv(self.residualCovariance).dot( measRes ) ) <= sigma2

	def _generateZeroHypothesis(self,time, scanNumber, P_d):
		NLLR = hpf.nllr(P_d)
		return self.clone(	time = time,
							scanNumber = scanNumber, 
							measurementNumber = 0,
							state = self.predictedStateMean, 
							covariance = self.predictedStateCovariance, 
							cummulativeNLLR = self.cummulativeNLLR + NLLR
						)

	def _pruneAllHypothesisExeptThis(self, keep):
		for hyp in self.trackHypotheses:
			if hyp != keep:
				self.trackHypotheses.remove(hyp)

	def plotInitial(self, index):
		plt.plot(self.filteredStateMean[0],self.filteredStateMean[1],"k+")
		ax = plt.subplot(111)
		normVelocity = self.filteredStateMean[2:4] / np.linalg.norm(self.filteredStateMean[2:4])
		offset = 0.1 * normVelocity
		position = self.filteredStateMean[0:2] - offset
		ax.text(position[0], position[1], "T"+str(index), 
			fontsize=8, horizontalalignment = "center", verticalalignment = "center")

	def getMeasurementSet(self, root = True):
		subSet = set()
		for hyp in self.trackHypotheses:
			subSet |= hyp.getMeasurementSet(False) 
		if (self.measurementNumber == 0) or (root):
			return subSet
		else:
			return {(self.scanNumber, self.measurementNumber)} | subSet

	def processNewMeasurement(self, measurementList, scanNumber, 
		associatedMeasurements, P_d, lambda_ex):
		if len(self.trackHypotheses) == 0:
			self.predictMeasurement(self.A,self.Q, self.Gamma, self.C, self.R)
			self.gateAndCreateNewHypotheses(measurementList, P_d, lambda_ex, scanNumber,associatedMeasurements)
		else:
			for hyp in self.trackHypotheses:
				hyp.processNewMeasurement(measurementList, scanNumber,associatedMeasurements, P_d, lambda_ex)

class Tracker():
	def __init__(self, timeStep, Phi, C, Gamma, P_d, P0, R, Q, 
						lambda_phi, lambda_nu, sigma, N, solver):
		#Tracker storage
		self.__targetList__ 	= []
		self.__associatedMeasurements__ = []
		self.__scanHistory__ = []
		self.__trackNodes__ = []
		
		#Tracker parameters
		self.P_d 		= P_d	
		self.lambda_phi = lambda_phi			
		self.lambda_nu 	= lambda_nu				
		self.lambda_ex 	= lambda_phi+lambda_nu 
		self.sigma 		= sigma
		self.sigma2		= np.power(sigma,2)	
		self.N 		 	= N
		self.solver  	= solver
		self.problemSizeLimit = 10000

		#State space model
		self.Phi 		= Phi
		self.T 			= timeStep
		self.A 			= Phi(timeStep) 				
		self.b 			= np.zeros(4) 			
		self.C 			= C
		self.d 			= np.zeros(2)			
		self.Gamma 		= Gamma
		self.P0 		= P0
		self.R 			= R	
		self.Q			= Q

	def initiateTarget(self,newTarget):
		target = Target(	time 		= newTarget.time, 
							scanNumber 	=  len(self.__scanHistory__),
							state 		= newTarget.state, 
							covariance 	= self.P0,
							A 			= self.A,
							Q  			= self.Q,
							Gamma 		= self.Gamma,
							C 			= self.C,
							sigma 		= self.sigma,
							R 			= self.R
							)
		self.__targetList__.append(target)
		self.__associatedMeasurements__.append( set() )
		target.plotInitial(len(self.__targetList__)-1)

	def addMeasurementList(self,measurementList):
		tic1 = time.clock()
		tic2 = time.clock()
		self.__scanHistory__.append(measurementList)
		scanNumber = len(self.__scanHistory__)
		nMeas = len(measurementList.measurements)
		nTargets = len(self.__targetList__)
		toc2 = time.clock() - tic2
		tic3 = time.clock()
		for targetIndex, target in enumerate(self.__targetList__):
			#estimate, gate and score new measurement
			target.processNewMeasurement(measurementList, scanNumber, self.__associatedMeasurements__[targetIndex],self.P_d, self.lambda_ex)
		toc3 = time.clock() - tic2
		# print(*__associatedMeasurements__, sep = "\n", end = "\n\n")
		#--Cluster targets--
		tic4 = time.clock()
		clusterList = self._findClustersFromSets()
		toc4 = time.clock() - tic4
		# hpf.printClusterList(clusterList)

		#--Maximize global (cluster vise) likelihood--
		tic5 = time.clock()
		globalHypotheses = np.empty(len(self.__targetList__),dtype = np.dtype(object))
		for cluster in clusterList:
			if len(cluster) == 1:
				# _pruneSmilarState(self.__targetList__[cluster[0]], 1)
				best = _selectBestHypothesis(self.__targetList__[cluster[0]])
				globalHypotheses[cluster] = best
			else:
				globalHypotheses[cluster] = _solveOptimumAssociation(cluster)
		toc5 = time.clock()-tic5
		tic6 = time.clock()
		# _nScanPruning(self.__trackNodes__, N)
		toc6 = time.clock()-tic6
		toc1 = time.clock() - tic1
		print(	"Added scan number:", scanNumber,
				" \tnMeas ", nMeas,
				" \tTotal time ", '{:5.4f}'.format(toc1),
				"\tListAdd ",	'{:5.4f}'.format(toc2),
				"\tProcess ",	'{:5.4f}'.format(toc3),
				"\tCluster ",	'{:5.4f}'.format(toc4),
				"\tOptim ",	'{:5.4f}'.format(toc5),
				"\tPrune ",	'{:5.4f}'.format(toc6),
				sep = "")
		self.__trackNodes__ = globalHypotheses
		return globalHypotheses

	def _findClustersFromSets(self):
		superSet = set() #TODO: This should be done a more elegant way!
		for targetIndex, targetSet in enumerate(self.__associatedMeasurements__):
			superSet |= targetSet
		nTargets = len(self.__associatedMeasurements__)
		nNodes = nTargets + len(superSet)
		adjacencyMatrix  = np.zeros((nNodes,nNodes),dtype=bool)
		for targetIndex, targetSet in enumerate(self.__associatedMeasurements__):
			for measurementIndex, measurement in enumerate(superSet):
				adjacencyMatrix[targetIndex,measurementIndex+nTargets] = (measurement in targetSet)
		# print("Adjacency Matrix2:\n", adjacencyMatrix.astype(dtype = int), sep = "", end = "\n\n")
		(nClusters, labels) = scipy.sparse.csgraph.connected_components(adjacencyMatrix)
		return [np.where(labels[:nTargets]==clusterIndex)[0].tolist() for clusterIndex in range(nClusters)]

	def getTrackNodes(self):
		return self.__trackNodes__