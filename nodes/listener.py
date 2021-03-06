#!/usr/bin/env python
import roslib; roslib.load_manifest('wifiScanner')
import rospy
from std_msgs.msg import String
import numpy as np
import scipy.optimize as optimize
from pylab import *
import tf

#global dictionary used here
apData = dict() #Storage of scan information
apLocs = dict() #storage of locations
counter = 0 #counter of scans for diagnostic info
recentScan = dict()

def callback(data):
	#this means data has been obtained from the listener
	#parse data into components and place in dictionary
    	if(data.data=="END_SCAN"):
		global counter
		counter+=1
		copyAps = dict(apLocs)
		copyAps = mergeAPs()
		broadcastAPs(copyAps)
		PosEstimate()
		recentScan.clear()
		return
	else:
		#this means data has been obtained from the listener
		#parse data into components and place in dictionary
		dataInfo=data.data.split()
		mac=dataInfo[0]
		#dataTuple=tuple(dataInfo[1:6])
		#dataTuple is in format
		#(signalStrength, x, y ,z, bssid)
		#Linear Model
		dataInfo[1] = 3 + (100-int(dataInfo[1]))/3

		#Quadratic Model
		#dataInfo[1] = 3 + ((100-int(dataInfo[1]))/5)**2

		#Piecewise Model
		#if(int(dataInfo[1]) == 100):
		# dataInfo[1] = 3
		#elif(int(dataInfo[1]) >= 70):
		# dataInfo[1] = 3 + (100-int(dataInfo[1]))/5
		#else: #Quadratic part?
		# dataInfo[1] = 9 + ((100-int(dataInfo[1]))/5)**2

		#Model based on the 3 access points we know of

		if mac in apData:
			#data for key/mac address exists
			apData[mac].append(dataTuple)
		else:
			#mac address is new
			apData[mac]=[dataTuple]
		recentScan[mac] = [dataTuple]
		#print apData[mac]
		#now perform the analysis on each of the ap entries
		pointNum=len(apData[mac])
		calcAPLocation(mac, pointNum)

def loadFileData(filename):
	rospy.init_node('listener', anonymous=True)	
	#loads data points from a file instead of from ros topic
	fin=open(filename)
	for data in fin:
		#this means data has been obtained from the listener
		#parse data into components and place in dictionary
		dataInfo=data.split()
		mac=dataInfo[0]
		dataTuple=tuple(dataInfo[1:6])
		#dataTuple is in format
		#(signalStrength, x, y ,z, bssid)
		#global apData
		if mac in apData:
			#data for key/mac address exists
			apData[mac].append(dataTuple)
		else:
			#mac address is new
			apData[mac]=[dataTuple]
		#print apData[mac]
		#now perform the analysis on each of the ap entries
		pointNum=len(apData[mac])
		calcAPLocation(mac, pointNum)
		copyAps = dict(apLocs)
		copyAps=mergeAPs()
		broadcastAPs(copyAps)

#Calculate the Location of the access point with MAC Address mac
def calcAPLocation(mac,pointNum):
	#if there are more than 2 data points for each AP, then we can perform the calculation
	#print "{0}\t{1}".format(mac,len(apData[mac]))
	if pointNum>=2:
		#average the centers of the circles
		sumX = 0.0
		sumY = 0.0
		#Also get all xi, yi, and radii for this access point in arrays
		#They will be needed for least squares, allows a single loop through
		xi = []
		yi = []
		radii = []
		for dataPt in apData[mac]:
			sumX+=float(dataPt[1])
			sumY+=float(dataPt[2])
			xi.append(float(dataPt[1]))
			yi.append(float(dataPt[2]))
			radii.append(float(dataPt[0]))
		avgX = sumX/pointNum
		avgY = sumY/pointNum
		#print "Average X: {0}\tY:{1}".format(avgX,avgY)
		#Now that we have the center, we can do least squares
		#generate point guess starting at avg of circles
		ptGuess = np.array([avgX,avgY])
		#If a current location already exist for the ap, use that as the guess
		if mac in apLocs:
			ptGuess = np.array([apLocs[mac][0],apLocs[mac][1]])
		#Convert arrays to type used by least squares
		#xi_p = np.array(xi)
		#yi_p = np.array(yi)
		#radii_p = np.array(radii)				
		point= optimize.leastsq(calcResiduals, ptGuess, args = (xi,yi,radii))
		#print point
		apLocs[mac] = [0,0,0]
		apLocs[mac][0]=point[0][0]
		apLocs[mac][1]=point[0][1]	
	


#Function that calculates and generates the residuals for a function
def calcResiduals(ptGuess, xi, yi, radii):
	#extract x and y from guess point
	xg = ptGuess[0]
	yg = ptGuess[1]
	#slope of the line from (xi,yi) to guess (xg,yg)
	m = (yg - yi) / (xg - xi)
	#Go along the line for the distance of c to get coordinates
	deltax = radii / np.sqrt(1+m**2)
	xii = []
	yii = []
	for i in range(0, len(xi)):		
		if (xi[i] < xg):
			xii.append(xi[i] + deltax[i])
		else:
			xii.append(xi[i] - deltax[i])
		yii.append(m[i]*(xii[i]-xi[i]) + yi[i])
	#residuals is distance from (xii,yii) to (xg, yg)
	return (xii-xg)**2 + (yii-yg)**2	


#Take the dictionary of all access points and average the locations of 
#Access points that are physically the same
#This is based off the RIT network, where the mac addresses differ
#in only the last 4 bits.
def mergeAPs():
	#go through all mac addresses in dictionary
	copyAps=dict(apLocs)
	for mac in copyAps.keys():
		for mac2 in copyAps.keys():
			#If same except last 4 bits(last hex char)
			if mac[:-1] == mac2[:-1] and mac != mac2:
				if ((mac[-1]=='0' or mac[-1]=='1' or mac[-1]=='2') and (mac2[-1]=='0' or mac2[-1]=='1' or mac2[-1]=='2')) or ((mac[-1]=='D' or mac[-1]=='E' or mac[-1]=='F') and (mac2[-1]=='D' or mac2[-1]=='E' or mac2[-1]=='F')):
					#Average together and store in mac
					if mac in copyAps and mac2 in copyAps:
						copyAps[mac][0] = (apLocs[mac][0]+apLocs[mac2][0])/2.0
						copyAps[mac][1] = (apLocs[mac][1]+apLocs[mac2][1])/2.0
						copyAps[mac][2] = (apLocs[mac][2]+apLocs[mac2][2])/2.0
						#remove mac2
						copyAps.pop(mac2)
	print "Scan {0}\n".format(counter)
	print copyAps
	print "-------------------------------------------\n"
	print "-------------------------------------------\n"
	return copyAps

#Broadcast all of the access point locations
#as ros transforms relative to the base
def broadcastAPs(copyAps):
	bc = tf.TransformBroadcaster()
	for mac in copyAps:
		bc.sendTransform((copyAps[mac][0],copyAps[mac][1],copyAps[mac][2]),
				tf.transformations.quaternion_from_euler(0,0,0),
				rospy.Time.now(),
				mac,
				"map")
	return

#Take the most recent scan results and use as a means of comparison to estimate the robot's location.
def PosEstimate():
    #copyAps contains a list of all the transforms aka AP Estimates
    #Take most recent scan results.
    #Iterate through all data in that scan, get the distances
	#also go through copyAps to get the locations to use as x,y coords
	xi = []
	yi = []
	radii = []
	ptGuess = np.array([0,0])
	for mac in recentScan.keys():
		xi.append(copyAps[mac][0])
		yi.append(copyAps[mac][1])
		radii.append(recentScan[mac][0])
		ptGuess = np.array([recentScan[mac][1],recentScan[mac][2]])
	point= optimize.leastsq(calcResiduals, ptGuess, args = (xi,yi,radii))
	print point
	#Broadcast Pt as a transform?
	bc = tf.TransformBroadcaster()
	bc.sendTransform((point[0][0],point[0][1],0),
			tf.transformations.quaternion_from_euler(0,0,0),
			rospy.Time.now(),
			"wifiLoc",
			"map")
    	return

def listener():
    rospy.init_node('listener', anonymous=True)
    rospy.Subscriber("aps", String, callback)
    rospy.spin()

if __name__ == '__main__':
    listener()
    #loadFileData("test1.txt")
