function cg_dsd_build(m)
% CG_DSD_BUILD  Builds the closed-loop model CabinGuardDSD.slx from REAL blocks only (no MATLAB Function blocks).
%   Scenario   : Scenario Reader (DSD road + shoulder + follower), ego pose comes from the vehicle model (input port)
%   Sensors    : Vision Detection Generator (lanes), Radar Detection Generator (rear), wheel-speed sensor with noise
%   Navigation : Bus Selector / Selector / Sum / Gain / Unit Delay / Compare blocks (lane geometry, lane-switch tracker, radar gap)
%   Guidance   : Clock, Step, Transfer Fcn (smooth lane-change reference), Rate Limiter + Integrator (speed profile)
%   Control    : Lane Keeping Assist System (MPC block) for steering, PID Controller block for speed, Saturation Dynamic (Gateway clamp)
%   Vehicle    : dynamic bicycle model in world coordinates (Integrator, Transfer Fcn, Rate Limiter, Fcn blocks)
if nargin < 1, m = 'CabinGuardDSD'; end
here = fileparts(mfilename('fullpath'));  cd(here);  addpath(here);
cg_dsd_bus();
load_system('drivingscenarioandsensors');  load_system('mpcadaslib');
% default workspace variables so the model can be updated before the first run
defs = {'cg_v0', 15.3; 'cg_psi0', 0; 'cg_X0', 0; 'cg_Y0', 0; 'cg_t_act', 5; 'cg_a_mrm', -3.2; 'cg_ysh', 3.6; 'cg_lw', 3.6; ...
        'cg_jump_thr', 2.7; 'cg_wn', 0.8; 'cg_lka_in', 1; 'cg_lka_out', 1; 'cg_a_clamp', -4; 'cg_ctl_mode', 0; 'cg_lka_beh', 0.3; 'cg_lka_lag', 0.1};
for k = 1:size(defs, 1)
    if ~evalin('base', sprintf('exist(''%s'',''var'')', defs{k,1})), assignin('base', defs{k,1}, defs{k,2}); end
end
assignin('base', 'cg_nn', cg_dsd_nn_default());          % always start from the placeholder network (a stale one from an older build would have the wrong size)
if ~evalin('base', 'exist(''cg_scn'',''var'')')
    sc0 = cg_dsd_scenario(struct());  assignin('base', 'cg_scn', sc0);
end
if bdIsLoaded(m), close_system(m, 0); end
new_system(m);
set_param(m, 'SolverType', 'Fixed-step', 'Solver', 'ode4', 'FixedStep', '0.01', 'StopTime', '30', 'SaveTime', 'on', 'TimeSaveName', 'tout', ...
    'ReturnWorkspaceOutputs', 'on');
try, set_param(m, 'SolverMode', 'SingleTasking'); catch, end

P = struct('m', 1500, 'Izz', 2500, 'a', 1.2, 'b', 1.5, 'mu', 0.9, 'g', 9.81);
P.L = P.a + P.b;  P.Caf = 12*P.m*P.g*P.b/P.L;  P.Car = 12*P.m*P.g*P.a/P.L;

%% ---- top level: scenario + sensors
add(m, 'drivingscenarioandsensors/Scenario Reader', 'SR', 'ScenarioSource', 'From workspace', 'ScenarioVariableName', 'cg_scn', ...
    'EgoVehicleSource', 'Input port', 'OutputCoordinateSystem', 'Vehicle coordinates', 'LaneBoundaryOutput', 'Ego vehicle lane boundaries', ...
    'LaneBoundaryDistance', '0:1:30', 'SampleTime', '0.1');
% 'Lanes only' skips the lane-occlusion test (about 3x faster); the follower is seen by the rear radar, not by the camera
add(m, 'drivingscenarioandsensors/Vision Detection Generator', 'Vision', 'DetectorOutput', 'Lanes only');
visPorts = get_param([m '/Vision'], 'Ports');
add(m, 'drivingscenarioandsensors/Radar Detection Generator', 'Radar', 'SensorLocation', '[-1 0]', 'Yaw', '180', 'DetectionCoordinates', 'Ego Cartesian', ...
    'HasFalseAlarms', 'off');
buildVehicle(m, P);
buildGNC(m, P);

% ego pose -> bus
add(m, 'simulink/Sources/Constant', 'Zero', 'Value', '0');
add(m, 'simulink/Sources/Constant', 'ActorID', 'Value', '1');
add(m, 'simulink/Signal Routing/Mux', 'PosMux', 'Inputs', '3');
add(m, 'simulink/Signal Routing/Mux', 'VelMux', 'Inputs', '3');
add(m, 'simulink/Signal Routing/Mux', 'AngMux', 'Inputs', '3');
add(m, 'simulink/Math Operations/Reshape', 'PosRs', 'OutputDimensionality', 'Customize', 'OutputDimensions', '[1 3]');
add(m, 'simulink/Math Operations/Reshape', 'VelRs', 'OutputDimensionality', 'Customize', 'OutputDimensions', '[1 3]');
add(m, 'simulink/Math Operations/Reshape', 'AngRs', 'OutputDimensionality', 'Customize', 'OutputDimensions', '[1 3]');
add(m, 'simulink/Math Operations/Gain', 'YawDeg', 'Gain', '180/pi');
add(m, 'simulink/Math Operations/Gain', 'RDeg', 'Gain', '180/pi');
add(m, 'simulink/Signal Routing/Bus Creator', 'EgoBus', 'Inputs', '7', 'UseBusObject', 'on', 'BusObject', 'cgEgoIn', 'NonVirtualBus', 'off');
L = { 'Vehicle/1','PosMux/1'; 'Vehicle/2','PosMux/2'; 'Zero/1','PosMux/3'; 'PosMux/1','PosRs/1'; ...
      'Vehicle/8','VelMux/1'; 'Vehicle/9','VelMux/2'; 'Zero/1','VelMux/3'; 'VelMux/1','VelRs/1'; ...
      'Zero/1','AngMux/1'; 'Zero/1','AngMux/2'; 'Vehicle/6','RDeg/1'; 'RDeg/1','AngMux/3'; 'AngMux/1','AngRs/1'; ...
      'Vehicle/3','YawDeg/1'; ...
      'ActorID/1','EgoBus/1'; 'PosRs/1','EgoBus/2'; 'VelRs/1','EgoBus/3'; 'Zero/1','EgoBus/4'; 'Zero/1','EgoBus/5'; 'YawDeg/1','EgoBus/6'; 'AngRs/1','EgoBus/7'; ...
      'EgoBus/1','SR/1'; 'SR/1','Radar/1'; 'Radar/1','GNC/2'; 'Vehicle/4','GNC/3'; 'GNC/1','Vehicle/1'; 'GNC/2','Vehicle/2'};
% (Vehicle inputs 1,2 are dcmd, acmd - the two GNC outputs)
for k = 1:size(L, 1), ln(m, L{k,1}, L{k,2}); end
if visPorts(1) == 1
    ln(m, 'SR/2', 'Vision/1');  ln(m, 'Vision/1', 'GNC/1');                      % lanes only: lane boundaries in, lane detections out
else
    ln(m, 'SR/1', 'Vision/1');  ln(m, 'SR/2', 'Vision/2');  ln(m, 'Vision/2', 'GNC/1');
    add(m, 'simulink/Sinks/Terminator', 'TermObj');  ln(m, 'Vision/1', 'TermObj/1');
end

% fault guard: stop (cleanly, keeping the log) the moment a controller output is not a number
add(m, 'simulink/Logic and Bit Operations/Relational Operator', 'NanSteer', 'Operator', '~=');
add(m, 'simulink/Logic and Bit Operations/Relational Operator', 'NanAcc', 'Operator', '~=');
add(m, 'simulink/Logic and Bit Operations/Logical Operator', 'NanOr', 'Operator', 'OR', 'Inputs', '2');
add(m, 'simulink/Sinks/Stop Simulation', 'GuardStop');
G = {'GNC/1','NanSteer/1'; 'GNC/1','NanSteer/2'; 'GNC/2','NanAcc/1'; 'GNC/2','NanAcc/2'; 'NanSteer/1','NanOr/1'; 'NanAcc/1','NanOr/2'; 'NanOr/1','GuardStop/1'};
for k = 1:size(G, 1), ln(m, G{k,1}, G{k,2}); end

% follower truth (for logging / metrics only)
add(m, 'simulink/Signal Routing/Bus Selector', 'FBS1', 'OutputSignals', 'Actors');
add(m, 'simulink/Signal Routing/Bus Selector', 'FBS2', 'OutputSignals', 'Position');
add(m, 'simulink/Math Operations/Reshape', 'FRs', 'OutputDimensionality', '1-D array');
ln(m, 'SR/1', 'FBS1/1');  ln(m, 'FBS1/1', 'FBS2/1');  ln(m, 'FBS2/1', 'FRs/1');
% log vector: X Y psi vx vy r delta | dbg(11) | follower position(3)
add(m, 'simulink/Signal Routing/Mux', 'LogMux', 'Inputs', '9');
for k = 1:7, ln(m, sprintf('Vehicle/%d', k), sprintf('LogMux/%d', k)); end
ln(m, 'GNC/3', 'LogMux/8');  ln(m, 'FRs/1', 'LogMux/9');
add(m, 'simulink/Sinks/To Workspace', 'Log', 'VariableName', 'cglog', 'SaveFormat', 'Array', 'SampleTime', '0.02', 'MaxDataPoints', 'inf');
ln(m, 'LogMux/1', 'Log/1');
add(m, 'simulink/Sinks/To Workspace', 'LogF', 'VariableName', 'cgfeat', 'SaveFormat', 'Array', 'SampleTime', '0.1', 'MaxDataPoints', 'inf');
add(m, 'simulink/Sinks/To Workspace', 'LogT', 'VariableName', 'cgtgt', 'SaveFormat', 'Array', 'SampleTime', '0.1', 'MaxDataPoints', 'inf');
ln(m, 'GNC/4', 'LogF/1');  ln(m, 'GNC/5', 'LogT/1');

try, Simulink.BlockDiagram.arrangeSystem(m); catch, end
try
    set_param(m, 'SimulationCommand', 'update');
    fprintf('Model update: OK\n');
catch e
    fprintf('Model update FAILED:\n%s\n', e.message);
    if ~isempty(e.cause), for c = 1:numel(e.cause), fprintf('  cause: %s\n', e.cause{c}.message); end, end
end
save_system(m, fullfile(here, m));
fprintf('Saved %s.slx\n', m);
end

%% ===================================================================== vehicle
function buildVehicle(m, P)
s = newSub(m, 'Vehicle', {'dcmd', 'acmd'}, {'X', 'Y', 'psi', 'vx', 'vy', 'r', 'delta', 'Xd', 'Yd'});
muFzf = P.mu * P.m * P.g * P.b / P.L;  muFzr = P.mu * P.m * P.g * P.a / P.L;
add(s, 'simulink/Discontinuities/Rate Limiter', 'SteerRL', 'RisingSlewLimit', '0.8', 'FallingSlewLimit', '-0.8');
add(s, 'simulink/Continuous/Transfer Fcn', 'SteerLag', 'Numerator', '1', 'Denominator', '[0.1 1]');
add(s, 'simulink/Continuous/Transfer Fcn', 'AccLag', 'Numerator', '1', 'Denominator', '[0.15 1]');
add(s, 'simulink/Discontinuities/Saturation', 'AccSat', 'UpperLimit', '3', 'LowerLimit', sprintf('%g', -P.mu * P.g));
add(s, 'simulink/Continuous/Integrator', 'Ivy', 'InitialCondition', '0');
add(s, 'simulink/Continuous/Integrator', 'Ir', 'InitialCondition', '0');
add(s, 'simulink/Continuous/Integrator', 'Ivx', 'InitialCondition', 'cg_v0', 'LimitOutput', 'on', 'UpperSaturationLimit', 'inf', 'LowerSaturationLimit', '0');
add(s, 'simulink/Continuous/Integrator', 'Ipsi', 'InitialCondition', 'cg_psi0');
add(s, 'simulink/Continuous/Integrator', 'IX', 'InitialCondition', 'cg_X0');
add(s, 'simulink/Continuous/Integrator', 'IY', 'InitialCondition', 'cg_Y0');
add(s, 'simulink/Discontinuities/Saturation', 'Vxe', 'UpperLimit', 'inf', 'LowerLimit', '1');
add(s, 'simulink/Signal Routing/Mux', 'MuxAF', 'Inputs', '4');
add(s, 'simulink/Signal Routing/Mux', 'MuxAR', 'Inputs', '3');
add(s, 'simulink/User-Defined Functions/Fcn', 'AlphaF', 'Expr', sprintf('u[1]-atan((u[2]+%g*u[3])/u[4])', P.a));
add(s, 'simulink/User-Defined Functions/Fcn', 'AlphaR', 'Expr', sprintf('-atan((u[1]-%g*u[2])/u[3])', P.b));
add(s, 'simulink/User-Defined Functions/Fcn', 'FyF', 'Expr', sprintf('%g*tanh(%g*u/%g)', muFzf, P.Caf, muFzf));
add(s, 'simulink/User-Defined Functions/Fcn', 'FyR', 'Expr', sprintf('%g*tanh(%g*u/%g)', muFzr, P.Car, muFzr));
add(s, 'simulink/Signal Routing/Mux', 'MuxVy', 'Inputs', '5');
add(s, 'simulink/Signal Routing/Mux', 'MuxR', 'Inputs', '3');
add(s, 'simulink/Signal Routing/Mux', 'MuxVx', 'Inputs', '4');
add(s, 'simulink/Signal Routing/Mux', 'MuxPos', 'Inputs', '3');
add(s, 'simulink/User-Defined Functions/Fcn', 'VyDot', 'Expr', sprintf('(u[1]*cos(u[2])+u[3])/%g-u[4]*u[5]', P.m));
add(s, 'simulink/User-Defined Functions/Fcn', 'RDot', 'Expr', sprintf('(%g*u[1]*cos(u[2])-%g*u[3])/%g', P.a, P.b, P.Izz));
add(s, 'simulink/User-Defined Functions/Fcn', 'VxDot', 'Expr', sprintf('u[1]+u[2]*u[3]-%g*u[4]^2-%g*tanh(5*u[4])', 0.5*1.2*0.7/P.m, 0.01*P.g));
add(s, 'simulink/User-Defined Functions/Fcn', 'XDot', 'Expr', 'u[1]*cos(u[3])-u[2]*sin(u[3])');
add(s, 'simulink/User-Defined Functions/Fcn', 'YDot', 'Expr', 'u[1]*sin(u[3])+u[2]*cos(u[3])');
W = { 'dcmd/1','SteerRL/1'; 'SteerRL/1','SteerLag/1'; 'acmd/1','AccLag/1'; 'AccLag/1','AccSat/1'; ...
      'Ivx/1','Vxe/1'; ...
      'SteerLag/1','MuxAF/1'; 'Ivy/1','MuxAF/2'; 'Ir/1','MuxAF/3'; 'Vxe/1','MuxAF/4'; 'MuxAF/1','AlphaF/1'; 'AlphaF/1','FyF/1'; ...
      'Ivy/1','MuxAR/1'; 'Ir/1','MuxAR/2'; 'Vxe/1','MuxAR/3'; 'MuxAR/1','AlphaR/1'; 'AlphaR/1','FyR/1'; ...
      'FyF/1','MuxVy/1'; 'SteerLag/1','MuxVy/2'; 'FyR/1','MuxVy/3'; 'Ivx/1','MuxVy/4'; 'Ir/1','MuxVy/5'; 'MuxVy/1','VyDot/1'; 'VyDot/1','Ivy/1'; ...
      'FyF/1','MuxR/1'; 'SteerLag/1','MuxR/2'; 'FyR/1','MuxR/3'; 'MuxR/1','RDot/1'; 'RDot/1','Ir/1'; ...
      'AccSat/1','MuxVx/1'; 'Ivy/1','MuxVx/2'; 'Ir/1','MuxVx/3'; 'Ivx/1','MuxVx/4'; 'MuxVx/1','VxDot/1'; 'VxDot/1','Ivx/1'; ...
      'Ir/1','Ipsi/1'; ...
      'Ivx/1','MuxPos/1'; 'Ivy/1','MuxPos/2'; 'Ipsi/1','MuxPos/3'; 'MuxPos/1','XDot/1'; 'MuxPos/1','YDot/1'; 'XDot/1','IX/1'; 'YDot/1','IY/1'; ...
      'IX/1','X/1'; 'IY/1','Y/1'; 'Ipsi/1','psi/1'; 'Ivx/1','vx/1'; 'Ivy/1','vy/1'; 'Ir/1','r/1'; 'SteerLag/1','delta/1'; 'XDot/1','Xd/1'; 'YDot/1','Yd/1'};
for k = 1:size(W, 1), ln(s, W{k,1}, W{k,2}); end
try, Simulink.BlockDiagram.arrangeSystem(s); catch, end
end

%% ===================================================================== GNC
function buildGNC(m, P) %#ok<INUSD>
g = newSub(m, 'GNC', {'Lanes', 'Radar', 'vx'}, {'dcmd', 'acmd', 'dbg', 'feat', 'tgt'});
buildNav(g);  buildGuid(g);  buildCtl(g);
% Navigation outs: 1 e1,2 e2,3 kappa,4 vmeas,5 gap,6 relv,7 d
% Guidance outs: 1 yref,2 ydot,3 vref,4 aref,5 act,6 actd,7 up,8 lo     (input: vmeas not needed)
% Control ins: 1 d,2 e2,3 kappa,4 vmeas,5 yref,6 ydot,7 vref,8 aref,9 act,10 up,11 lo ; outs: 1 dcmd, 2 acmd
W = { 'Lanes/1','Navigation/1'; 'Radar/1','Navigation/2'; 'vx/1','Navigation/3'; ...
      'Navigation/7','Control/1'; 'Navigation/2','Control/2'; 'Navigation/3','Control/3'; 'Navigation/4','Control/4'; ...
      'Guidance/1','Control/5'; 'Guidance/2','Control/6'; 'Guidance/3','Control/7'; 'Guidance/4','Control/8'; 'Guidance/5','Control/9'; ...
      'Guidance/7','Control/10'; 'Guidance/8','Control/11'; ...
      'Control/1','dcmd/1'; 'Control/2','acmd/1'; 'Control/3','feat/1'; 'Control/4','tgt/1'};
for k = 1:size(W, 1), ln(g, W{k,1}, W{k,2}); end
add(g, 'simulink/Signal Routing/Mux', 'DbgMux', 'Inputs', '11');
D = { 'Navigation/1','DbgMux/1'; 'Navigation/7','DbgMux/2'; 'Guidance/1','DbgMux/3'; 'Guidance/3','DbgMux/4'; 'Guidance/4','DbgMux/5'; 'Guidance/6','DbgMux/6'; ...
      'Navigation/5','DbgMux/7'; 'Navigation/6','DbgMux/8'; 'Navigation/4','DbgMux/9'; 'Control/2','DbgMux/10'; 'Control/1','DbgMux/11'; 'DbgMux/1','dbg/1'};
for k = 1:size(D, 1), ln(g, D{k,1}, D{k,2}); end
try, Simulink.BlockDiagram.arrangeSystem(g); catch, end
end

%% ===================================================================== navigation
function buildNav(g)
s = newSub(g, 'Navigation', {'Lanes', 'Radar', 'vx'}, {'e1', 'e2', 'kappa', 'vmeas', 'gap', 'relv', 'd'});
BS = 'simulink/Signal Routing/Bus Selector';  SEL = 'simulink/Signal Routing/Selector';
% --- lane geometry from the two ego-lane boundaries (1 = left, 2 = right)
add(s, BS, 'LBS', 'OutputSignals', 'LaneBoundaries,NumLaneBoundaries');
add(s, SEL, 'Lane1', 'IndexMode', 'One-based', 'NumberOfDimensions', '1', 'IndexOptionArray', {'Index vector (dialog)'}, 'IndexParamArray', {'1'}, 'InputPortWidth', '-1');
add(s, SEL, 'Lane2', 'IndexMode', 'One-based', 'NumberOfDimensions', '1', 'IndexOptionArray', {'Index vector (dialog)'}, 'IndexParamArray', {'2'}, 'InputPortWidth', '-1');
add(s, BS, 'B1', 'OutputSignals', 'LateralOffset,HeadingAngle,Curvature');
add(s, BS, 'B2', 'OutputSignals', 'LateralOffset,HeadingAngle,Curvature');
add(s, 'simulink/Math Operations/Sum', 'sOff', 'Inputs', '++');
add(s, 'simulink/Math Operations/Sum', 'sHd', 'Inputs', '++');
add(s, 'simulink/Math Operations/Sum', 'sCv', 'Inputs', '++');
add(s, 'simulink/Math Operations/Gain', 'gOff', 'Gain', '-0.5');
add(s, 'simulink/Math Operations/Gain', 'gHd', 'Gain', '-0.5*pi/180');
add(s, 'simulink/Math Operations/Gain', 'gCv', 'Gain', '0.5*pi/180');
add(s, 'simulink/Logic and Bit Operations/Compare To Constant', 'Valid', 'relop', '>=', 'const', '2');
% a boundary can be reported as 'present' while its numbers are NaN: accept a sample only if it is also finite
add(s, 'simulink/Math Operations/Sum', 'FinSum', 'Inputs', '+++');
add(s, 'simulink/Math Operations/Abs', 'FinAbs');
add(s, 'simulink/Logic and Bit Operations/Compare To Constant', 'FinCmp', 'relop', '<', 'const', '1000');
add(s, 'simulink/Logic and Bit Operations/Logical Operator', 'GoodAnd', 'Operator', 'AND', 'Inputs', '2');
for nm = {'1', '2', '3'}
    add(s, 'simulink/Signal Routing/Switch', ['H' nm{1}], 'Criteria', 'u2 ~= 0');
    add(s, 'simulink/Discrete/Unit Delay', ['Hd' nm{1}], 'InitialCondition', '0', 'SampleTime', '0.1');
end
W = { 'Lanes/1','LBS/1'; 'LBS/1','Lane1/1'; 'LBS/1','Lane2/1'; 'Lane1/1','B1/1'; 'Lane2/1','B2/1'; ...
      'B1/1','sOff/1'; 'B2/1','sOff/2'; 'B1/2','sHd/1'; 'B2/2','sHd/2'; 'B1/3','sCv/1'; 'B2/3','sCv/2'; ...
      'sOff/1','gOff/1'; 'sHd/1','gHd/1'; 'sCv/1','gCv/1'; 'LBS/2','Valid/1'; 'gOff/1','FinSum/1'; 'gHd/1','FinSum/2'; 'gCv/1','FinSum/3'; 'FinSum/1','FinAbs/1'; 'FinAbs/1','FinCmp/1'; 'Valid/1','GoodAnd/1'; 'FinCmp/1','GoodAnd/2'; ...
      'gOff/1','H1/1'; 'GoodAnd/1','H1/2'; 'Hd1/1','H1/3'; 'H1/1','Hd1/1'; ...
      'gHd/1','H2/1'; 'GoodAnd/1','H2/2'; 'Hd2/1','H2/3'; 'H2/1','Hd2/1'; ...
      'gCv/1','H3/1'; 'GoodAnd/1','H3/2'; 'Hd3/1','H3/3'; 'H3/1','Hd3/1'; ...
      'H1/1','e1/1'; 'H2/1','e2/1'; 'H3/1','kappa/1'};
for k = 1:size(W, 1), ln(s, W{k,1}, W{k,2}); end
% --- lane-switch tracker: when the ego crosses into the next lane the measured offset jumps by one lane width.
%     N counts the crossings, d = offset from the ORIGINAL lane centre (continuous).
add(s, 'simulink/Discrete/Unit Delay', 'PrevE1', 'InitialCondition', '0', 'SampleTime', '0.1');
add(s, 'simulink/Math Operations/Sum', 'Jump', 'Inputs', '+-');
add(s, 'simulink/Logic and Bit Operations/Compare To Constant', 'JumpUp', 'relop', '>', 'const', 'cg_jump_thr');
add(s, 'simulink/Logic and Bit Operations/Compare To Constant', 'JumpDn', 'relop', '<', 'const', '-cg_jump_thr');
add(s, 'simulink/Signal Attributes/Data Type Conversion', 'CvUp', 'OutDataTypeStr', 'double');
add(s, 'simulink/Signal Attributes/Data Type Conversion', 'CvDn', 'OutDataTypeStr', 'double');
add(s, 'simulink/Math Operations/Sum', 'Step', 'Inputs', '+-');
add(s, 'simulink/Math Operations/Sum', 'Nsum', 'Inputs', '++');
add(s, 'simulink/Discrete/Unit Delay', 'Nd', 'InitialCondition', '0', 'SampleTime', '0.1');
add(s, 'simulink/Math Operations/Gain', 'LW', 'Gain', 'cg_lw');
add(s, 'simulink/Math Operations/Sum', 'DSum', 'Inputs', '+-');
W = { 'H1/1','PrevE1/1'; 'H1/1','Jump/1'; 'PrevE1/1','Jump/2'; 'Jump/1','JumpUp/1'; 'Jump/1','JumpDn/1'; 'JumpUp/1','CvUp/1'; 'JumpDn/1','CvDn/1'; ...
      'CvUp/1','Step/1'; 'CvDn/1','Step/2'; 'Step/1','Nsum/1'; 'Nd/1','Nsum/2'; 'Nsum/1','Nd/1'; 'Nsum/1','LW/1'; ...
      'H1/1','DSum/1'; 'LW/1','DSum/2'; 'DSum/1','d/1'};
for k = 1:size(W, 1), ln(s, W{k,1}, W{k,2}); end
% --- wheel-speed sensor: true speed + noise, sampled at 10 Hz
add(s, 'simulink/Sources/Random Number', 'WsNoise', 'Mean', '0', 'Variance', '0.0025', 'Seed', '7', 'SampleTime', '0.1');
add(s, 'simulink/Math Operations/Sum', 'WsSum', 'Inputs', '++');
add(s, 'simulink/Discrete/Zero-Order Hold', 'WsZoh', 'SampleTime', '0.1');
W = { 'vx/1','WsSum/1'; 'WsNoise/1','WsSum/2'; 'WsSum/1','WsZoh/1'; 'WsZoh/1','vmeas/1'};
for k = 1:size(W, 1), ln(s, W{k,1}, W{k,2}); end
% --- rear radar: first detection -> distance behind and closing speed
add(s, BS, 'RBS', 'OutputSignals', 'Detections,NumDetections');
add(s, SEL, 'Det1', 'IndexMode', 'One-based', 'NumberOfDimensions', '1', 'IndexOptionArray', {'Index vector (dialog)'}, 'IndexParamArray', {'1'}, 'InputPortWidth', '-1');
add(s, BS, 'RB2', 'OutputSignals', 'Measurement');
add(s, 'simulink/Math Operations/Reshape', 'RRs', 'OutputDimensionality', '1-D array');
add(s, SEL, 'RSel', 'IndexMode', 'One-based', 'NumberOfDimensions', '1', 'InputPortWidth', '6', 'IndexOptionArray', {'Index vector (dialog)'}, 'IndexParamArray', {'[1 4]'});
add(s, 'simulink/Signal Routing/Demux', 'RDm', 'Outputs', '2');
add(s, 'simulink/Math Operations/Gain', 'GapG', 'Gain', '-1');
add(s, 'simulink/Logic and Bit Operations/Compare To Constant', 'RValid', 'relop', '>=', 'const', '1');
add(s, 'simulink/Sources/Constant', 'NoGap', 'Value', '999');
add(s, 'simulink/Sources/Constant', 'NoRel', 'Value', '0');
add(s, 'simulink/Signal Routing/Switch', 'GapSw', 'Criteria', 'u2 ~= 0');
add(s, 'simulink/Signal Routing/Switch', 'RelSw', 'Criteria', 'u2 ~= 0');
W = { 'Radar/1','RBS/1'; 'RBS/1','Det1/1'; 'Det1/1','RB2/1'; 'RB2/1','RRs/1'; 'RRs/1','RSel/1'; 'RSel/1','RDm/1'; 'RDm/1','GapG/1'; ...
      'RBS/2','RValid/1'; 'GapG/1','GapSw/1'; 'RValid/1','GapSw/2'; 'NoGap/1','GapSw/3'; 'RDm/2','RelSw/1'; 'RValid/1','RelSw/2'; 'NoRel/1','RelSw/3'; ...
      'GapSw/1','gap/1'; 'RelSw/1','relv/1'};
for k = 1:size(W, 1), ln(s, W{k,1}, W{k,2}); end
try, Simulink.BlockDiagram.arrangeSystem(s); catch, end
end

%% ===================================================================== guidance
function buildGuid(g)
s = newSub(g, 'Guidance', {}, {'yref', 'ydot', 'vref', 'aref', 'act', 'actd', 'up', 'lo'});
add(s, 'simulink/Sources/Clock', 'Clk');
add(s, 'simulink/Logic and Bit Operations/Compare To Constant', 'Active', 'relop', '>=', 'const', 'cg_t_act');
add(s, 'simulink/Signal Attributes/Data Type Conversion', 'ActD', 'OutDataTypeStr', 'double');
% smooth lane-change reference (critically damped 2nd order) and its derivative
add(s, 'simulink/Sources/Step', 'LcStep', 'Time', 'cg_t_act', 'Before', '0', 'After', '1', 'SampleTime', '0');
add(s, 'simulink/Continuous/Transfer Fcn', 'LcY', 'Numerator', 'cg_wn^2', 'Denominator', '[1 2*cg_wn cg_wn^2]');
add(s, 'simulink/Continuous/Transfer Fcn', 'LcYd', 'Numerator', '[cg_wn^2 0]', 'Denominator', '[1 2*cg_wn cg_wn^2]');
add(s, 'simulink/Math Operations/Gain', 'YshY', 'Gain', '-cg_ysh');
add(s, 'simulink/Math Operations/Gain', 'YshYd', 'Gain', '-cg_ysh');
% speed profile: requested decel, jerk limited, integrated to a speed reference
add(s, 'simulink/Sources/Constant', 'AMrm', 'Value', 'cg_a_mrm');
add(s, 'simulink/Sources/Constant', 'AZero', 'Value', '0');
add(s, 'simulink/Signal Routing/Switch', 'ASw', 'Criteria', 'u2 ~= 0');
add(s, 'simulink/Discontinuities/Rate Limiter', 'Jerk', 'RisingSlewLimit', '5', 'FallingSlewLimit', '-5');
add(s, 'simulink/Continuous/Integrator', 'VRef', 'InitialCondition', 'cg_v0', 'LimitOutput', 'on', 'UpperSaturationLimit', 'inf', 'LowerSaturationLimit', '0');
% Gateway clamp limits: while active -4 <= a_mrm <= a <= 0 ; otherwise [-6, +2]
add(s, 'simulink/Sources/Constant', 'UpAct', 'Value', '0');
add(s, 'simulink/Sources/Constant', 'UpIdle', 'Value', '2');
add(s, 'simulink/Signal Routing/Switch', 'UpSw', 'Criteria', 'u2 ~= 0');
add(s, 'simulink/Sources/Constant', 'ClampMax', 'Value', 'cg_a_clamp');
add(s, 'simulink/Math Operations/MinMax', 'LoMax', 'Function', 'max', 'Inputs', '2');
add(s, 'simulink/Sources/Constant', 'LoIdle', 'Value', '-6');
add(s, 'simulink/Signal Routing/Switch', 'LoSw', 'Criteria', 'u2 ~= 0');
W = { 'Clk/1','Active/1'; 'Active/1','ActD/1'; 'LcStep/1','LcY/1'; 'LcStep/1','LcYd/1'; 'LcY/1','YshY/1'; 'LcYd/1','YshYd/1'; ...
      'AMrm/1','ASw/1'; 'Active/1','ASw/2'; 'AZero/1','ASw/3'; 'ASw/1','Jerk/1'; 'Jerk/1','VRef/1'; ...
      'UpAct/1','UpSw/1'; 'Active/1','UpSw/2'; 'UpIdle/1','UpSw/3'; ...
      'ClampMax/1','LoMax/1'; 'AMrm/1','LoMax/2'; 'LoMax/1','LoSw/1'; 'Active/1','LoSw/2'; 'LoIdle/1','LoSw/3'; ...
      'YshY/1','yref/1'; 'YshYd/1','ydot/1'; 'VRef/1','vref/1'; 'Jerk/1','aref/1'; 'Active/1','act/1'; 'ActD/1','actd/1'; 'UpSw/1','up/1'; 'LoSw/1','lo/1'};
for k = 1:size(W, 1), ln(s, W{k,1}, W{k,2}); end
try, Simulink.BlockDiagram.arrangeSystem(s); catch, end
end

%% ===================================================================== control
function buildCtl(g)
s = newSub(g, 'Control', {'d', 'e2', 'kappa', 'vmeas', 'yref', 'ydot', 'vref', 'aref', 'act', 'up', 'lo'}, {'dcmd', 'acmd', 'feat', 'tgt'});
% ---- steering: Lane Keeping Assist System (MPC) block
lka = add(s, 'mpcadaslib/Lane Keeping Assist System', 'LKA', 'ModelType', 'Use vehicle parameters', 'VehicleMass', '1500', 'VehicleYawInertia', '2500', ...
    'LengthToFront', '1.2', 'LengthToRear', '1.5', 'FrontTireStiffness', '98100', 'RearTireStiffness', '78480', 'InitialLongVel', '15', ...
    'TransportLag', 'cg_lka_lag', 'MinSteering', '-0.1', 'MaxSteering', '0.1', 'Ts', '0.1', 'PredictionHorizon', '10', 'ControllerBehavior', 'cg_lka_beh'); %#ok<NASGU>
add(s, 'simulink/Sources/Constant', 'ModeC', 'Value', 'cg_ctl_mode');
add(s, 'simulink/Signal Routing/Switch', 'SteerSel', 'Criteria', 'u2 ~= 0');
add(s, 'simulink/Signal Routing/Switch', 'AccSel', 'Criteria', 'u2 ~= 0');
% safety layer: whatever the driver is (MPC block or network), the front-wheel angle never exceeds the actuator limit of 0.1 rad
add(s, 'simulink/Discontinuities/Saturation', 'SteerLim', 'UpperLimit', '0.1', 'LowerLimit', '-0.1');
add(s, 'simulink/Signal Attributes/Data Type Conversion', 'ActDbl', 'OutDataTypeStr', 'double');
add(s, 'simulink/Signal Routing/Mux', 'FeatMux', 'Inputs', '11');
% short memory for the network: lane offset and heading error of the previous two 0.1 s steps (the MPC block estimates lateral velocity and yaw rate from this history)
for nm = {'DevD1', 'DevD2', 'YawD1', 'YawD2'}
    add(s, 'simulink/Discrete/Unit Delay', nm{1}, 'InitialCondition', '0', 'SampleTime', '0.1');
end
add(s, 'simulink/Signal Routing/Mux', 'TgtMux', 'Inputs', '2');
buildNN(s);
add(s, 'simulink/Math Operations/Sum', 'DevErr', 'Inputs', '+-');
add(s, 'simulink/Discontinuities/Saturation', 'VxeS', 'UpperLimit', 'inf', 'LowerLimit', '2');
add(s, 'simulink/Math Operations/Product', 'YdDivV', 'Inputs', '*/');
add(s, 'simulink/Math Operations/Sum', 'YawErr', 'Inputs', '+-');
add(s, 'simulink/Math Operations/Gain', 'InDev', 'Gain', 'cg_lka_in');
add(s, 'simulink/Math Operations/Gain', 'InYaw', 'Gain', 'cg_lka_in');
add(s, 'simulink/Math Operations/Gain', 'InKap', 'Gain', 'cg_lka_in');
add(s, 'simulink/Discontinuities/Saturation', 'VLka', 'UpperLimit', '40', 'LowerLimit', '1');
add(s, 'simulink/Math Operations/Gain', 'OutSt', 'Gain', 'cg_lka_out');
add(s, 'simulink/Sources/Constant', 'StraightC', 'Value', '0');
add(s, 'simulink/Signal Routing/Switch', 'StSw', 'Criteria', 'u2 >= Threshold', 'Threshold', '0.5');
W = { 'd/1','DevErr/1'; 'yref/1','DevErr/2'; 'DevErr/1','InDev/1'; ...
      'vmeas/1','VxeS/1'; 'ydot/1','YdDivV/1'; 'VxeS/1','YdDivV/2'; 'e2/1','YawErr/1'; 'YdDivV/1','YawErr/2'; 'YawErr/1','InYaw/1'; ...
      'kappa/1','InKap/1'; 'vmeas/1','VLka/1'; ...
      'InKap/1','LKA/1'; 'VLka/1','LKA/2'; 'InDev/1','LKA/3'; 'InYaw/1','LKA/4'; ...
      'LKA/1','OutSt/1'; 'OutSt/1','SteerSel/3'; 'SteerSel/1','SteerLim/1'; 'SteerLim/1','StSw/1'; 'vmeas/1','StSw/2'; 'StraightC/1','StSw/3'; 'StSw/1','dcmd/1'};
for k = 1:size(W, 1), ln(s, W{k,1}, W{k,2}); end
% ---- speed: PID Controller block + feed-forward of the profile acceleration, Gateway clamp via Saturation Dynamic
add(s, 'simulink/Math Operations/Sum', 'VErr', 'Inputs', '+-');
add(s, 'simulink/Continuous/PID Controller', 'SpeedPID', 'Controller', 'PI', 'TimeDomain', 'Discrete-time', 'SampleTime', '0.1', ...
    'P', '1.2', 'I', '0.25', 'LimitOutput', 'on', 'UpperSaturationLimit', '2', 'LowerSaturationLimit', '-6', 'AntiWindupMode', 'clamping');
add(s, 'simulink/Math Operations/Sum', 'FF', 'Inputs', '++');
add(s, 'simulink/Discontinuities/Saturation Dynamic', 'GwClamp');
add(s, 'simulink/Logic and Bit Operations/Compare To Constant', 'Slow', 'relop', '<', 'const', '0.3');
add(s, 'simulink/Logic and Bit Operations/Logical Operator', 'HoldAnd', 'Operator', 'AND', 'Inputs', '2');
add(s, 'simulink/Sources/Constant', 'HoldA', 'Value', '-1.5');
add(s, 'simulink/Signal Routing/Switch', 'HoldSw', 'Criteria', 'u2 ~= 0');
W = { 'vref/1','VErr/1'; 'vmeas/1','VErr/2'; 'VErr/1','SpeedPID/1'; 'SpeedPID/1','FF/1'; 'aref/1','FF/2'; ...
      'up/1','GwClamp/1'; 'FF/1','AccSel/3'; 'AccSel/1','GwClamp/2'; 'lo/1','GwClamp/3'; ...
      'vmeas/1','Slow/1'; 'act/1','HoldAnd/1'; 'Slow/1','HoldAnd/2'; ...
      'HoldA/1','HoldSw/1'; 'HoldAnd/1','HoldSw/2'; 'GwClamp/1','HoldSw/3'; 'HoldSw/1','acmd/1'};
for k = 1:size(W, 1), ln(s, W{k,1}, W{k,2}); end
W = { 'DevErr/1','FeatMux/1'; 'YawErr/1','FeatMux/2'; 'kappa/1','FeatMux/3'; 'vmeas/1','FeatMux/4'; 'VErr/1','FeatMux/5'; 'aref/1','FeatMux/6'; ...
      'act/1','ActDbl/1'; 'ActDbl/1','FeatMux/7'; 'DevErr/1','DevD1/1'; 'DevD1/1','DevD2/1'; 'YawErr/1','YawD1/1'; 'YawD1/1','YawD2/1'; ...
      'DevD1/1','FeatMux/8'; 'YawD1/1','FeatMux/9'; 'DevD2/1','FeatMux/10'; 'YawD2/1','FeatMux/11'; 'FeatMux/1','feat/1'; 'FeatMux/1','NN/1'; 'NN/1','SteerSel/1'; 'NN/2','AccSel/1'; ...
      'ModeC/1','SteerSel/2'; 'ModeC/1','AccSel/2'; 'OutSt/1','TgtMux/1'; 'FF/1','TgtMux/2'; 'TgtMux/1','tgt/1'};
for k = 1:size(W, 1), ln(s, W{k,1}, W{k,2}); end
try, Simulink.BlockDiagram.arrangeSystem(s); catch, end
end

%% ===================================================================== learned policy (built from real blocks)
function buildNN(ctl)
% 11 features -> 64 -> 64 -> 2 (steering [rad], acceleration [m/s^2]); weights live in the workspace struct cg_nn (see cg_dsd_train)
s = newSub(ctl, 'NN', {'feat'}, {'steer', 'acc'});
add(s, 'simulink/Discrete/Zero-Order Hold', 'Hold', 'SampleTime', '0.1');
add(s, 'simulink/Sources/Constant', 'MuIn', 'Value', 'cg_nn.mu_in');
add(s, 'simulink/Math Operations/Sum', 'Cen', 'Inputs', '+-');
add(s, 'simulink/Sources/Constant', 'IsdIn', 'Value', 'cg_nn.isd_in');
add(s, 'simulink/Math Operations/Product', 'Scl', 'Inputs', '**');
W = {'feat/1','Hold/1'; 'Hold/1','Cen/1'; 'MuIn/1','Cen/2'; 'Cen/1','Scl/1'; 'IsdIn/1','Scl/2'};
prev = 'Scl/1';
for k = 1:3
    add(s, 'simulink/Math Operations/Gain', sprintf('W%d', k), 'Gain', sprintf('cg_nn.W%d', k), 'Multiplication', 'Matrix(K*u)');
    add(s, 'simulink/Sources/Constant', sprintf('bc%d', k), 'Value', sprintf('cg_nn.b%d', k));
    add(s, 'simulink/Math Operations/Sum', sprintf('B%d', k), 'Inputs', '++');
    W(end+1, :) = {prev, sprintf('W%d/1', k)}; %#ok<AGROW>
    W(end+1, :) = {sprintf('W%d/1', k), sprintf('B%d/1', k)}; %#ok<AGROW>
    W(end+1, :) = {sprintf('bc%d/1', k), sprintf('B%d/2', k)}; %#ok<AGROW>
    prev = sprintf('B%d/1', k);
    if k < 3
        add(s, 'simulink/Discontinuities/Saturation', sprintf('ReLU%d', k), 'UpperLimit', 'inf', 'LowerLimit', '0');
        W(end+1, :) = {prev, sprintf('ReLU%d/1', k)}; %#ok<AGROW>
        prev = sprintf('ReLU%d/1', k);
    end
end
add(s, 'simulink/Sources/Constant', 'SdOut', 'Value', 'cg_nn.sd_out');
add(s, 'simulink/Math Operations/Product', 'Den', 'Inputs', '**');
add(s, 'simulink/Sources/Constant', 'MuOut', 'Value', 'cg_nn.mu_out');
add(s, 'simulink/Math Operations/Sum', 'Off', 'Inputs', '++');
add(s, 'simulink/Signal Routing/Demux', 'Dm', 'Outputs', '2');
W = [W; {prev, 'Den/1'; 'SdOut/1', 'Den/2'; 'Den/1', 'Off/1'; 'MuOut/1', 'Off/2'; 'Off/1', 'Dm/1'; 'Dm/1', 'steer/1'; 'Dm/2', 'acc/1'}];
for k = 1:size(W, 1), ln(s, W{k,1}, W{k,2}); end
try, Simulink.BlockDiagram.arrangeSystem(s); catch, end
end

%% ===================================================================== helpers
function s = newSub(parent, name, ins, outs)
s = [parent '/' name];
add_block('simulink/Ports & Subsystems/Subsystem', s);
delete_line(s, 'In1/1', 'Out1/1');  delete_block([s '/In1']);  delete_block([s '/Out1']);
for i = 1:numel(ins),  add_block('simulink/Sources/In1',  [s '/' ins{i}],  'Port', num2str(i)); end
for i = 1:numel(outs), add_block('simulink/Sinks/Out1',   [s '/' outs{i}], 'Port', num2str(i)); end
end

function b = add(sys, lib, name, varargin)
b = [sys '/' name];
add_block(lib, b);
for k = 1:2:numel(varargin)
    try
        set_param(b, varargin{k}, varargin{k+1});
    catch e
        v = varargin{k+1};  if iscell(v), v = strjoin(v, ','); end
        fprintf('  [warn] %s: could not set %s = %s  (%s)\n', b, varargin{k}, v, strtok(e.message, newline));
    end
end
end

function ln(sys, a, b)
try
    add_line(sys, a, b, 'autorouting', 'on');
catch e
    error('Wiring %s: %s -> %s failed: %s', sys, a, b, e.message);
end
end
