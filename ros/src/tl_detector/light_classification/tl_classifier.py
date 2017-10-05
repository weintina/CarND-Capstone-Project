from styx_msgs.msg import TrafficLight

from 

class TLClassifier(object):
    def __init__(self):
        
        # TODO Load trained model

        # TODO Get parameters of model from ROS param server

        

    def get_classification(self, image):
        """Determines the color of the traffic light in the image

        Args:
            image (cv::Mat): image containing the traffic light

        Returns:
            int: ID of traffic light color (specified in styx_msgs/TrafficLight)

        """
        #TODO implement light color prediction
        return TrafficLight.UNKNOWN
