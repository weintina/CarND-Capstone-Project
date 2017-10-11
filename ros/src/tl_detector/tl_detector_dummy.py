#!/usr/bin/env python
import rospy
from std_msgs.msg import Int32
from geometry_msgs.msg import PoseStamped, Pose
from styx_msgs.msg import TrafficLightArray, TrafficLight
from styx_msgs.msg import Lane
from sensor_msgs.msg import Image
from cv_bridge import CvBridge
from light_classification.tl_classifier import TLClassifier
import tf
import cv2
import yaml

import math
import numpy as np


STATE_COUNT_THRESHOLD = 3

class TLDetector(object):
    def __init__(self):
        rospy.init_node('tl_detector')

        self.position = None
        self.base_waypoints = None
        self.camera_image = None
        self.lights = []

        sub1 = rospy.Subscriber('/current_pose', PoseStamped, self.pose_cb)
        sub2 = rospy.Subscriber('/base_waypoints', Lane, self.waypoints_cb)

        '''
        /vehicle/traffic_lights provides you with the location of the traffic light in 3D map space and
        helps you acquire an accurate ground truth data source for the traffic light
        classifier by sending the current color state of all traffic lights in the
        simulator. When testing on the vehicle, the color state will not be available. You'll need to
        rely on the position of the light and the camera image to predict it.
        '''
        sub3 = rospy.Subscriber('/vehicle/traffic_lights', TrafficLightArray, self.traffic_cb)
        sub6 = rospy.Subscriber('/image_color', Image, self.image_cb)

        config_string = rospy.get_param("/traffic_light_config")
        self.config = yaml.load(config_string)

        self.upcoming_red_light_pub = rospy.Publisher('/traffic_waypoint', Int32, queue_size=1)

        self.bridge = CvBridge()
        self.light_classifier = TLClassifier()
        self.listener = tf.TransformListener()

        self.state = TrafficLight.UNKNOWN
        self.last_state = TrafficLight.UNKNOWN
        self.last_wp = -1
        self.state_count = 0

        rospy.spin()

    def pose_cb(self, msg):
        self.position = msg.pose.position

    def waypoints_cb(self, waypoints):
        self.base_waypoints = waypoints

    def traffic_cb(self, msg):
        self.lights = msg.lights

    def image_cb(self, msg):
        """Identifies red lights in the incoming camera image and publishes the index
            of the waypoint closest to the red light's stop line to /traffic_waypoint

        Args:
            msg (Image): image from car-mounted camera

        """
        self.has_image = True
        self.camera_image = msg
        light_wp, state = self.process_traffic_lights()

        '''
        Publish upcoming red lights at camera frequency.
        Each predicted state has to occur `STATE_COUNT_THRESHOLD` number
        of times till we start using it. Otherwise the previous stable state is
        used.
        '''
        if self.state != state:
            self.state_count = 0
            self.state = state
        elif self.state_count >= STATE_COUNT_THRESHOLD:
            self.last_state = self.state
            #light_wp = light_wp if state == TrafficLight.RED else -1
            if state == TrafficLight.RED or state == TrafficLight.YELLOW:
                light_wp = light_wp
            elif state == TrafficLight.GREEN:
                light_wp = -light_wp
            else :
                light_wp = 1000000

            self.last_wp = light_wp
            self.upcoming_red_light_pub.publish(Int32(light_wp))
        else:
            self.upcoming_red_light_pub.publish(Int32(self.last_wp))
        self.state_count += 1

    def get_closest_waypoint(self, x, y):
        """
        Identifies the closest path waypoint to the given position
            https://en.wikipedia.org/wiki/Closest_pair_of_points_problem
        Args:
            pose (Pose): position to match a waypoint to
        Returns:
            int: index of the closest waypoint in self.waypoints
        """
        # current position
        cur_pos_x = x
        cur_pos_y = y

        closest_dist = 999999.
        closest_wp = None

        wp_len = len(self.base_waypoints.waypoints)
        for i in range(wp_len):
            base_wp_x = self.base_waypoints.waypoints[i].pose.pose.position.x
            base_wp_y = self.base_waypoints.waypoints[i].pose.pose.position.y
            dist = math.sqrt(math.pow(cur_pos_x - base_wp_x, 2) + math.pow(cur_pos_y - base_wp_y, 2))
            if dist < closest_dist:
                closest_dist = dist
                closest_wp = i

        #Check if waypoint is ahead of vehicle
        closest_wp_x = self.base_waypoints.waypoints[closest_wp].pose.pose.position.x
        closest_wp_y = self.base_waypoints.waypoints[closest_wp].pose.pose.position.y

        return closest_wp

    def project_to_image_plane(self, point_in_world):
        """Project point from 3D world coordinates to 2D camera image location

        Args:
            point_in_world (Point): 3D location of a point in the world

        Returns:
            x (int): x coordinate of target point in image
            y (int): y coordinate of target point in image

        """

        fx = self.config['camera_info']['focal_length_x']
        fy = self.config['camera_info']['focal_length_y']
        image_width = self.config['camera_info']['image_width']
        image_height = self.config['camera_info']['image_height']

        # get transform between pose of camera and world frame
        trans = None
        try:
            now = rospy.Time.now()
            self.listener.waitForTransform("/base_link",
                  "/world", now, rospy.Duration(1.0))
            (trans, rot) = self.listener.lookupTransform("/base_link",
                  "/world", now)

        except (tf.Exception, tf.LookupException, tf.ConnectivityException):
            rospy.logerr("Failed to find camera to map transform")

        #TODO Use tranform and rotation to calculate 2D position of light in image

        x = 0
        y = 0

        return (x, y)

    def get_light_state(self, light):
        """Determines the current color of the traffic light

        Args:
            light (TrafficLight): light to classify

        Returns:
            int: ID of traffic light color (specified in styx_msgs/TrafficLight)

        """
        if(not self.has_image):
            self.prev_light_loc = None
            return False

        cv_image = self.bridge.imgmsg_to_cv2(self.camera_image, "bgr8")

        x, y = self.project_to_image_plane(light.pose.pose.position)

        #TODO use light location to zoom in on traffic light in image

        #Get classification
        return self.light_classifier.get_classification(cv_image)

    def process_traffic_lights(self):
        """Finds closest visible traffic light, if one exists, and determines its
            location and color

        Returns:
            int: index of waypoint closes to the upcoming stop line for a traffic light (-1 if none exists)
            int: ID of traffic light color (specified in styx_msgs/TrafficLight)

        """
        # List of positions that correspond to the line to stop in front of for a given intersection
        stop_line_positions = self.config['stop_line_positions']
        if self.base_waypoints == None :
            return -1, TrafficLight.UNKNOWN

        if self.position == None :
            return -1, TrafficLight.UNKNOWN

        car_position = self.get_closest_waypoint(self.position.x, self.position.y)

        #TODO find the closest visible traffic light (if one exists)
        tl_len = len(self.lights)
        closest_wp = -1
        tl_idx = -1
        for i in range(tl_len):
            tl_wp = self.get_closest_waypoint(
                            self.lights[i].pose.pose.position.x,
                            self.lights[i].pose.pose.position.y)
            if car_position < tl_wp:
                closest_wp = tl_wp
                tl_idx = i
                break

        if closest_wp == -1:
            return -1, TrafficLight.UNKNOWN

        sl_wp = self.get_closest_waypoint(
                    stop_line_positions[tl_idx][0], 
                    stop_line_positions[tl_idx][1]
                    )
        if sl_wp <= car_position:
            return -1, TrafficLight.UNKNOWN

        dist = self.distance(self.base_waypoints.waypoints, car_position, sl_wp) 
        if dist < 40.0:
            light = True
            light_wp = sl_wp
            state = self.lights[tl_idx].state
            # rospy.loginfo("now = %d, light = %d, dist = %d, state = %d", car_position, light_wp, dist, state) 
            return light_wp, state
        else:
            return -1, TrafficLight.UNKNOWN

    def distance(self, waypoints, wp1, wp2):
        dist = 0
        dl = lambda a, b: math.sqrt((a.x-b.x)**2 + (a.y-b.y)**2  + (a.z-b.z)**2)
        for i in range(wp1, wp2+1):
            dist += dl(waypoints[wp1].pose.pose.position, waypoints[i].pose.pose.position)
            wp1 = i
        return dist

if __name__ == '__main__':
    try:
        TLDetector()
    except rospy.ROSInterruptException:
        rospy.logerr('Could not start traffic node.')