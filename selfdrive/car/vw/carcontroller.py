from common.numpy_fast import clip, interp
from common.realtime import sec_since_boot
from selfdrive.config import Conversions as CV
from selfdrive.boardd.boardd import can_list_to_can_capnp
from selfdrive.car.vw.carstate import CarState, get_powertrain_can_parser
from selfdrive.car.vw import vwcan
from selfdrive.car.vw.values import CAR, DBC
from selfdrive.can.packer import CANPacker


class CarControllerParams():
  def __init__(self, car_fingerprint):
    self.STEER_MAX = 300               # max stock steer 300 
    self.STEER_STEP_OFF = 100          # how often we update the steer cmd
    self.STEER_STEP_ON = 2             # how often we update the steer cmd
    self.STEER_DELTA_UP = 10           # torque increase per refresh
    self.STEER_DELTA_DOWN = 10         # torque decrease per refresh
    self.STEER_DRIVER_ALLOWANCE = 20   # allowed driver torque before start limiting
    self.STEER_DRIVER_MULTIPLIER = 1   
    self.STEER_DRIVER_FACTOR = 1       
    


class CarController(object):
  def __init__(self, canbus, car_fingerprint):
    self.start_time = sec_since_boot()
    self.counter = 0
    self.apply_steer_last = 0
    self.car_fingerprint = car_fingerprint

    # Setup detection helper. Routes commands to
    # an appropriate CAN bus number.
    self.canbus = canbus
    self.params = CarControllerParams(car_fingerprint)
    print(DBC)
    self.packer_pt = CANPacker(DBC[car_fingerprint]['pt'])

  def update(self, sendcan, enabled, CS, frame, actuators):
    """ Controls thread """

    P = self.params

    # Send CAN commands.
    can_sends = []
    canbus = self.canbus

    ### STEER ###
    
    if enabled:  
      if (frame % P.STEER_STEP_ON) == 0:
        lkas_enabled = enabled and not CS.steer_not_allowed
        final_steer = actuators.steer if enabled else 0.
        apply_steer = final_steer * P.STEER_MAX
        # limits due to driver torque
        driver_max_torque = P.STEER_MAX + (P.STEER_DRIVER_ALLOWANCE + CS.steer_torque_driver * P.STEER_DRIVER_FACTOR) * P.STEER_DRIVER_MULTIPLIER
        driver_min_torque = -P.STEER_MAX + (-P.STEER_DRIVER_ALLOWANCE + CS.steer_torque_driver * P.STEER_DRIVER_FACTOR) * P.STEER_DRIVER_MULTIPLIER
        max_steer_allowed = max(min(P.STEER_MAX, driver_max_torque), 0)
        min_steer_allowed = min(max(-P.STEER_MAX, driver_min_torque), 0)
        apply_steer = clip(apply_steer, min_steer_allowed, max_steer_allowed)

        # slow rate if steer torque increases in magnitude
        if self.apply_steer_last > 0:
          apply_steer = clip(apply_steer, max(self.apply_steer_last - P.STEER_DELTA_DOWN, -P.STEER_DELTA_UP), self.apply_steer_last + P.STEER_DELTA_UP)
        else:
          apply_steer = clip(apply_steer, self.apply_steer_last - P.STEER_DELTA_UP, min(self.apply_steer_last + P.STEER_DELTA_DOWN, P.STEER_DELTA_UP))

        apply_steer = int(round(apply_steer))
        self.apply_steer_last = apply_steer

        if apply_steer != 0:
          steer = abs(apply_steer)
        counter += 1
        idx = counter % 16
        can_sends.append(vwcan.create_steering_control(self.packer_pt, canbus.powertrain, CS.CP.carFingerprint, steer, idx, lkas_enabled))

    else:
      if (frame % P.STEER_STEP_OFF) == 0:
        apply_steer = 0
        if counter < 1:
          counter = self.counter
        counter += 1
        idx = counter % 16
        lkas_enabled = 0
        can_sends.append(vwcan.create_steering_control(self.packer_pt, canbus.powertrain, CS.CP.carFingerprint, steer, idx, lkas_enabled))
    
    sendcan.send(can_list_to_can_capnp(can_sends, msgtype='sendcan').to_bytes())
