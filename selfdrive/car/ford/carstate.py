from selfdrive.can.parser import CANParser
from selfdrive.config import Conversions as CV
from selfdrive.car.ford.values import DBC
from common.kalman.simple_kalman import KF1D
import numpy as np

WHEEL_RADIUS = 0.33

def get_can_parser(CP):

  signals = [
    # sig_name, sig_address, default
    ("WhlRr_W_Meas", "WheelSpeed_CG1", 0.),
    ("WhlRl_W_Meas", "WheelSpeed_CG1", 0.),
    ("WhlFr_W_Meas", "WheelSpeed_CG1", 0.),
    ("WhlFl_W_Meas", "WheelSpeed_CG1", 0.),
    ("SteWhlRelInit_An_Sns", "Steering_Wheel_Data_CG1", 0.),
    ("CcStat_D_Actl", "EngBrakeData", 0.),
    ("Veh_V_DsplyCcSet", "EngBrakeData", 0.),
    ("LaActAvail_D_Actl", "Lane_Assist_Data3", 0),
    ("LaHandsOff_B_Actl", "Lane_Assist_Data3", 0),
    ("LaActDeny_B_Actl", "Lane_Assist_Data3", 0),
    ("ApedPosScal_Pc_Actl", "EngineData_14", 0.),
    ("BpedDrvAppl_D_Actl", "EngBrakeData", 0.),
    ("Brake_Lamp_On_Status", "BCM_to_HS_Body", 0.),
  ]

  checks = [
  ]

  return CANParser(DBC[CP.carFingerprint]['pt'], signals, checks, 0)


class CarState(object):
  def __init__(self, CP):

    self.CP = CP
    self.left_blinker_on = 0
    self.right_blinker_on = 0

    # initialize can parser
    self.car_fingerprint = CP.carFingerprint

    # vEgo kalman filter
    dt = 0.01
    # Q = np.matrix([[10.0, 0.0], [0.0, 100.0]])
    # R = 1e3
    self.v_ego_kf = KF1D(x0=np.matrix([[0.0], [0.0]]),
                         A=np.matrix([[1.0, dt], [0.0, 1.0]]),
                         C=np.matrix([1.0, 0.0]),
                         K=np.matrix([[0.12287673], [0.29666309]]))
    self.v_ego = 0.0

  def update(self, cp):
    # copy can_valid
    self.can_valid = cp.can_valid

    # update prevs, update must run once per loop
    self.prev_left_blinker_on = self.left_blinker_on
    self.prev_right_blinker_on = self.right_blinker_on

    # calc best v_ego estimate, by averaging two opposite corners
    self.v_wheel_fl = cp.vl["WheelSpeed_CG1"]['WhlRr_W_Meas'] * WHEEL_RADIUS
    self.v_wheel_fr = cp.vl["WheelSpeed_CG1"]['WhlRl_W_Meas'] * WHEEL_RADIUS
    self.v_wheel_rl = cp.vl["WheelSpeed_CG1"]['WhlFr_W_Meas'] * WHEEL_RADIUS
    self.v_wheel_rr = cp.vl["WheelSpeed_CG1"]['WhlFl_W_Meas'] * WHEEL_RADIUS
    self.v_wheel = float(np.mean([self.v_wheel_fl, self.v_wheel_fr, self.v_wheel_rl, self.v_wheel_rr]))

    # Kalman filter
    if abs(self.v_wheel - self.v_ego) > 2.0:  # Prevent large accelerations when car starts at non zero speed
      self.v_ego_x = np.matrix([[self.v_wheel], [0.0]])

    self.v_ego_raw = self.v_wheel
    v_ego_x = self.v_ego_kf.update(self.v_wheel)
    self.v_ego = float(v_ego_x[0])
    self.a_ego = float(v_ego_x[1])
    self.standstill = not self.v_wheel > 0.01

    self.angle_steers = cp.vl["Steering_Wheel_Data_CG1"]['SteWhlRelInit_An_Sns']
    self.steer_override = not cp.vl["Lane_Assist_Data3"]['LaHandsOff_B_Actl']
    self.user_gas = cp.vl["EngineData_14"]['ApedPosScal_Pc_Actl']
    self.brake_pressed = bool(cp.vl["EngBrakeData"]["BpedDrvAppl_D_Actl"])
    self.brake_lights = bool(cp.vl["BCM_to_HS_Body"]["Brake_Lamp_On_Status"])
    self.pcm_acc_status = cp.vl["EngBrakeData"]['CcStat_D_Actl']
    self.v_cruise_pcm = cp.vl["EngBrakeData"]['Veh_V_DsplyCcSet'] * CV.MPH_TO_MS

    self.main_on = cp.vl["EngBrakeData"]['CcStat_D_Actl'] != 0
    self.lkas_state = cp.vl["Lane_Assist_Data3"]['LaActAvail_D_Actl']
    self.steer_error = cp.vl["Lane_Assist_Data3"]['LaActDeny_B_Actl']
