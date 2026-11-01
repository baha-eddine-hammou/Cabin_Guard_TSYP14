function cg_auto_build(m)
% CG_AUTO_BUILD  Builds CabinGuardAuto.slx - the autonomous take-over car, from REAL blocks only (no MATLAB Function blocks).
%   Scenario   : Scenario Reader (any Driving Scenario: road, cars, pedestrians); ego pose comes from the vehicle model
%   Sensors    : Vision Detection Generator (lanes), 3 Radar Detection Generators (front, rear, right), wheel-speed sensor with noise
%   Navigation : lane geometry from the camera, lane-switch tracker (works across any number of lanes)
%   Perception : every radar detection is checked for "in my path" (curve- and motion-compensated) and "right side occupied"
%   Decision   : brake demand from the worst obstacle (cars AND pedestrians), move-right decision with latch
%   Guidance   : smooth lateral reference, jerk-limited speed profile
%   Control    : Lane Keeping Assist System (MPC) block + PID Controller block + Saturation Dynamic clamp
%   Vehicle    : dynamic bicycle model in world coordinates
if nargin < 1, m = 'CabinGuardAuto'; end
here = fileparts(mfilename('fullpath'));  cd(here);  addpath(here);
cg_dsd_bus();
load_system('drivingscenarioandsensors');  load_system('mpcadaslib');
defs = {'ca_v0', 15; 'ca_psi0', 0; 'ca_X0', 0; 'ca_Y0', 0; 'ca_ego_id', 1; 'ca_t_act', 5; 'ca_a_comf', 3.2; 'ca_clear', 5.4; 'ca_edge', 1.8; ...
        'ca_min_shift', 2.2; 'ca_hw', 1.5; 'ca_d0', 5; 'ca_wn', 1.0; 'ca_lka_in', 1; 'ca_lka_out', 1; 'ca_a_lo', -9; 'ca_lka_beh', 0.3; 'ca_lka_lag', 0.1; ...
        'ca_jdn', 20; 'ca_jup', 5; 'ca_lw0', 3.6; 'ca_absvel', 0; 'ca_vlat', 1.8; 'ca_kfeas', 0.8; 'ca_plant', 1; 'ca_sys', 0; 'ca_go_phase', 3; 'ca_pv', [0;0;15;0;1;4;-3;0;2;0;2;0;2;2;1]; 'ca_det', [1;1;0;0;0]};
for k = 1:size(defs, 1)
    if ~evalin('base', sprintf('exist(''%s'',''var'')', defs{k,1})), assignin('base', defs{k,1}, defs{k,2}); end
end
if ~evalin('base', 'exist(''ca_scn'',''var'')')
    sc0 = cg_auto_scene(struct());  assignin('base', 'ca_scn', sc0);
end
if bdIsLoaded(m), close_system(m, 0); end
new_system(m);
set_param(m, 'SolverType', 'Fixed-step', 'Solver', 'ode4', 'FixedStep', '0.01', 'StopTime', '30', 'SaveTime', 'on', 'TimeSaveName', 'tout', ...
    'ReturnWorkspaceOutputs', 'on');
try, set_param(m, 'SolverMode', 'SingleTasking'); catch, end

P = struct('m', 1500, 'Izz', 2500, 'a', 1.2, 'b', 1.5, 'mu', 0.9, 'g', 9.81);
P.L = P.a + P.b;  P.Caf = 12*P.m*P.g*P.b/P.L;  P.Car = 12*P.m*P.g*P.a/P.L;

%% ---- top level: scenario + sensors
add(m, 'drivingscenarioandsensors/Scenario Reader', 'SR', 'ScenarioSource', 'From workspace', 'ScenarioVariableName', 'ca_scn', ...
    'EgoVehicleSource', 'Input port', 'OutputCoordinateSystem', 'Vehicle coordinates', 'LaneBoundaryOutput', 'Ego vehicle lane boundaries', ...
    'LaneBoundaryDistance', '0:1:30', 'SampleTime', '0.1');
add(m, 'drivingscenarioandsensors/Vision Detection Generator', 'Vision', 'DetectorOutput', 'Lanes only');
visPorts = get_param([m '/Vision'], 'Ports');
% three radars: front (wide, long), rear, right side. Radars report cars AND pedestrians (RCS of the actor).
radar(m, 'RadF', 1, '[3.7 0]', '0',    '[100 10]', '150');
radar(m, 'RadR', 2, '[-1 0]',  '180',  '[60 10]',  '120');
radar(m, 'RadS', 3, '[2.0 -0.9]', '-90', '[150 10]', '30');
buildVehicle(m, P);
buildGNC(m, P);
cg_auto_system(m);      % CabinGuard layer: Driver, Faults, Host, Gateway, Telem -> take-over request for the GNC

% ego pose -> bus
add(m, 'simulink/Sources/Constant', 'Zero', 'Value', '0');
add(m, 'simulink/Sources/Constant', 'ActorID', 'Value', 'ca_ego_id');
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
      'EgoBus/1','SR/1'; 'SR/1','RadF/1'; 'SR/1','RadR/1'; 'SR/1','RadS/1'; ...
      'RadF/1','GNC/2'; 'RadR/1','GNC/3'; 'RadS/1','GNC/4'; 'Vehicle/4','GNC/5'; 'GNC/1','Vehicle/1'; 'GNC/2','Vehicle/2'};
for k = 1:size(L, 1), ln(m, L{k,1}, L{k,2}); end
if visPorts(1) == 1
    ln(m, 'SR/2', 'Vision/1');  ln(m, 'Vision/1', 'GNC/1');
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

% log vector: X Y psi vx vy r delta | dbg(13)
add(m, 'simulink/Signal Routing/Mux', 'LogMux', 'Inputs', '8');
for k = 1:7, ln(m, sprintf('Vehicle/%d', k), sprintf('LogMux/%d', k)); end
ln(m, 'GNC/3', 'LogMux/8');
add(m, 'simulink/Sinks/To Workspace', 'Log', 'VariableName', 'calog', 'SaveFormat', 'Array', 'SampleTime', '0.02', 'MaxDataPoints', 'inf');
ln(m, 'LogMux/1', 'Log/1');

% detailed longitudinal plant (Vehicle Dynamics Blockset); the model stays usable with the simple plant if this fails
try
    cg_auto_plant(m);
catch e
    fprintf('\n[warn] detailed plant NOT added: %s\n       The model works with the simple plant (ca_plant = 0).\n', e.message);
    assignin('base', 'ca_plant', 0);
end
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

function radar(m, name, idx, loc, yaw, fov, rng)
b = add(m, 'drivingscenarioandsensors/Radar Detection Generator', name, 'SensorLocation', loc, 'Yaw', yaw, 'DetectionCoordinates', 'Ego Cartesian', 'HasFalseAlarms', 'off');
setAny(b, {'SensorIndex'}, num2str(idx));
setAny(b, {'FieldOfView'}, fov);
setAny(b, {'RangeLimits', 'MaxRange'}, ['[0 ' rng ']'], rng);
setAny(b, {'MaxNumDetections', 'MaxNumReports', 'MaxNumDetectionsSource'}, '6');
end

function setAny(b, names, varargin)
% tries the parameter names in turn (the block parameter names differ a little between releases); prints a warning if none works
vals = varargin;  if numel(vals) < numel(names), vals(end+1:numel(names)) = vals(1); end
for k = 1:numel(names)
    try
        set_param(b, names{k}, vals{k});  return
    catch
    end
end
fprintf('  [warn] %s: none of %s could be set (%s)\n', b, strjoin(names, '/'), vals{1});
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
add(s, 'simulink/Continuous/Integrator', 'Ivx', 'InitialCondition', 'ca_v0', 'LimitOutput', 'on', 'UpperSaturationLimit', 'inf', 'LowerSaturationLimit', '0');
add(s, 'simulink/Continuous/Integrator', 'Ipsi', 'InitialCondition', 'ca_psi0');
add(s, 'simulink/Continuous/Integrator', 'IX', 'InitialCondition', 'ca_X0');
add(s, 'simulink/Continuous/Integrator', 'IY', 'InitialCondition', 'ca_Y0');
add(s, 'simulink/Discontinuities/Saturation', 'Vxe', 'UpperLimit', 'inf', 'LowerLimit', '1');
% speed selector: ca_plant = 1 -> speed of the detailed longitudinal plant (added by cg_auto_plant), 0 -> simple integrator Ivx
add(s, 'simulink/Math Operations/Gain', 'VxHi', 'Gain', '1');
add(s, 'simulink/Sources/Constant', 'PlantSel', 'Value', 'ca_plant');
add(s, 'simulink/Signal Routing/Switch', 'VxSel', 'Criteria', 'u2 ~= 0');
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
      'VxSel/1','Vxe/1'; 'Ivx/1','VxHi/1'; 'VxHi/1','VxSel/1'; 'PlantSel/1','VxSel/2'; 'Ivx/1','VxSel/3'; ...
      'SteerLag/1','MuxAF/1'; 'Ivy/1','MuxAF/2'; 'Ir/1','MuxAF/3'; 'Vxe/1','MuxAF/4'; 'MuxAF/1','AlphaF/1'; 'AlphaF/1','FyF/1'; ...
      'Ivy/1','MuxAR/1'; 'Ir/1','MuxAR/2'; 'Vxe/1','MuxAR/3'; 'MuxAR/1','AlphaR/1'; 'AlphaR/1','FyR/1'; ...
      'FyF/1','MuxVy/1'; 'SteerLag/1','MuxVy/2'; 'FyR/1','MuxVy/3'; 'VxSel/1','MuxVy/4'; 'Ir/1','MuxVy/5'; 'MuxVy/1','VyDot/1'; 'VyDot/1','Ivy/1'; ...
      'FyF/1','MuxR/1'; 'SteerLag/1','MuxR/2'; 'FyR/1','MuxR/3'; 'MuxR/1','RDot/1'; 'RDot/1','Ir/1'; ...
      'AccSat/1','MuxVx/1'; 'Ivy/1','MuxVx/2'; 'Ir/1','MuxVx/3'; 'Ivx/1','MuxVx/4'; 'MuxVx/1','VxDot/1'; 'VxDot/1','Ivx/1'; ...
      'Ir/1','Ipsi/1'; ...
      'VxSel/1','MuxPos/1'; 'Ivy/1','MuxPos/2'; 'Ipsi/1','MuxPos/3'; 'MuxPos/1','XDot/1'; 'MuxPos/1','YDot/1'; 'XDot/1','IX/1'; 'YDot/1','IY/1'; ...
      'IX/1','X/1'; 'IY/1','Y/1'; 'Ipsi/1','psi/1'; 'VxSel/1','vx/1'; 'Ivy/1','vy/1'; 'Ir/1','r/1'; 'SteerLag/1','delta/1'; 'XDot/1','Xd/1'; 'YDot/1','Yd/1'};
for k = 1:size(W, 1), ln(s, W{k,1}, W{k,2}); end
try, Simulink.BlockDiagram.arrangeSystem(s); catch, end
end

%% ===================================================================== GNC
function buildGNC(m, P) %#ok<INUSD>
g = newSub(m, 'GNC', {'Lanes', 'RadF', 'RadR', 'RadS', 'vx', 'go'}, {'dcmd', 'acmd', 'dbg'});
buildNav(g);  buildPerc(g);  buildDec(g);  buildGuid(g);  buildCtl(g);
% Navigation  in: Lanes, vx            out: 1 e1, 2 e2, 3 kappa, 4 vmeas, 5 d
% Perception  in: RF, RR, RS, kappa, vmeas   out: 1 areq, 2 occ
% Decision    in: areq, occ, vmeas, go  out: 1 ulat, 2 adem, 3 act, 4 yshT, 5 commit
% Guidance    in: adem, ulat, go       out: 1 yref, 2 ydot, 3 vref, 4 aref, 5 act, 6 actd, 7 up, 8 lo
% Control     in: d,e2,kappa,vmeas,yref,ydot,vref,aref,act,up,lo   out: 1 dcmd, 2 acmd
W = { 'Lanes/1','Navigation/1'; 'vx/1','Navigation/2'; ...
      'RadF/1','Perception/1'; 'RadR/1','Perception/2'; 'RadS/1','Perception/3'; 'Navigation/3','Perception/4'; 'Navigation/4','Perception/5'; ...
      'Perception/1','Decision/1'; 'Perception/2','Decision/2'; 'Navigation/4','Decision/3'; 'go/1','Decision/4'; 'go/1','Guidance/3'; ...
      'Decision/2','Guidance/1'; 'Decision/1','Guidance/2'; ...
      'Navigation/5','Control/1'; 'Navigation/2','Control/2'; 'Navigation/3','Control/3'; 'Navigation/4','Control/4'; ...
      'Guidance/1','Control/5'; 'Guidance/2','Control/6'; 'Guidance/3','Control/7'; 'Guidance/4','Control/8'; 'Guidance/5','Control/9'; ...
      'Guidance/7','Control/10'; 'Guidance/8','Control/11'; 'Control/1','dcmd/1'; 'Control/2','acmd/1'};
for k = 1:size(W, 1), ln(g, W{k,1}, W{k,2}); end
add(g, 'simulink/Signal Attributes/Data Type Conversion', 'OccD', 'OutDataTypeStr', 'double');
add(g, 'simulink/Signal Routing/Mux', 'DbgMux', 'Inputs', '13');
D = { 'Navigation/1','DbgMux/1'; 'Navigation/5','DbgMux/2'; 'Guidance/1','DbgMux/3'; 'Guidance/3','DbgMux/4'; 'Guidance/4','DbgMux/5'; 'Guidance/6','DbgMux/6'; ...
      'Decision/2','DbgMux/7'; 'Perception/1','DbgMux/8'; 'Perception/2','OccD/1'; 'OccD/1','DbgMux/9'; 'Decision/5','DbgMux/10'; 'Decision/4','DbgMux/11'; ...
      'Control/2','DbgMux/12'; 'Control/1','DbgMux/13'; 'DbgMux/1','dbg/1'};
for k = 1:size(D, 1), ln(g, D{k,1}, D{k,2}); end
try, Simulink.BlockDiagram.arrangeSystem(g); catch, end
end

%% ===================================================================== navigation
function buildNav(g)
s = newSub(g, 'Navigation', {'Lanes', 'vx'}, {'e1', 'e2', 'kappa', 'vmeas', 'd'});
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
add(s, 'simulink/Math Operations/Sum', 'sWd', 'Inputs', '+-');
add(s, 'simulink/Math Operations/Gain', 'gOff', 'Gain', '-0.5');
add(s, 'simulink/Math Operations/Gain', 'gHd', 'Gain', '-0.5*pi/180');
add(s, 'simulink/Math Operations/Gain', 'gCv', 'Gain', '0.5*pi/180');
add(s, 'simulink/Logic and Bit Operations/Compare To Constant', 'Valid', 'relop', '>=', 'const', '2');
% a boundary can be reported as 'present' while its numbers are NaN: accept a sample only if it is also finite
add(s, 'simulink/Math Operations/Sum', 'FinSum', 'Inputs', '+++');
add(s, 'simulink/Math Operations/Abs', 'FinAbs');
add(s, 'simulink/Logic and Bit Operations/Compare To Constant', 'FinCmp', 'relop', '<', 'const', '1000');
add(s, 'simulink/Logic and Bit Operations/Logical Operator', 'GoodAnd', 'Operator', 'AND', 'Inputs', '2');
for nm = {'1', '2', '3', '4'}
    ic = '0';  if strcmp(nm{1}, '4'), ic = 'ca_lw0'; end
    add(s, 'simulink/Signal Routing/Switch', ['H' nm{1}], 'Criteria', 'u2 ~= 0');
    add(s, 'simulink/Discrete/Unit Delay', ['Hd' nm{1}], 'InitialCondition', ic, 'SampleTime', '0.1');
end
W = { 'Lanes/1','LBS/1'; 'LBS/1','Lane1/1'; 'LBS/1','Lane2/1'; 'Lane1/1','B1/1'; 'Lane2/1','B2/1'; ...
      'B1/1','sOff/1'; 'B2/1','sOff/2'; 'B1/2','sHd/1'; 'B2/2','sHd/2'; 'B1/3','sCv/1'; 'B2/3','sCv/2'; 'B1/1','sWd/1'; 'B2/1','sWd/2'; ...
      'sOff/1','gOff/1'; 'sHd/1','gHd/1'; 'sCv/1','gCv/1'; 'LBS/2','Valid/1'; ...
      'gOff/1','FinSum/1'; 'gHd/1','FinSum/2'; 'gCv/1','FinSum/3'; 'FinSum/1','FinAbs/1'; 'FinAbs/1','FinCmp/1'; 'Valid/1','GoodAnd/1'; 'FinCmp/1','GoodAnd/2'; ...
      'gOff/1','H1/1'; 'GoodAnd/1','H1/2'; 'Hd1/1','H1/3'; 'H1/1','Hd1/1'; ...
      'gHd/1','H2/1'; 'GoodAnd/1','H2/2'; 'Hd2/1','H2/3'; 'H2/1','Hd2/1'; ...
      'gCv/1','H3/1'; 'GoodAnd/1','H3/2'; 'Hd3/1','H3/3'; 'H3/1','Hd3/1'; ...
      'sWd/1','H4/1'; 'GoodAnd/1','H4/2'; 'Hd4/1','H4/3'; 'H4/1','Hd4/1'; ...
      'H1/1','e1/1'; 'H2/1','e2/1'; 'H3/1','kappa/1'};
for k = 1:size(W, 1), ln(s, W{k,1}, W{k,2}); end
% --- lane-switch tracker: when the ego crosses into the next lane the measured offset jumps by one lane width.
%     round(jump / lane width) counts the lanes crossed (any number), d = offset from the ORIGINAL lane centre (continuous).
add(s, 'simulink/Discrete/Unit Delay', 'PrevE1', 'InitialCondition', '0', 'SampleTime', '0.1');
add(s, 'simulink/Math Operations/Sum', 'Jump', 'Inputs', '+-');
add(s, 'simulink/Math Operations/Product', 'JDiv', 'Inputs', '*/');
add(s, 'simulink/Math Operations/Rounding Function', 'JRnd', 'Operator', 'round');
add(s, 'simulink/Math Operations/Product', 'JMul', 'Inputs', '**');
add(s, 'simulink/Math Operations/Sum', 'Nsum', 'Inputs', '++');
add(s, 'simulink/Discrete/Unit Delay', 'Nd', 'InitialCondition', '0', 'SampleTime', '0.1');
add(s, 'simulink/Math Operations/Sum', 'DSum', 'Inputs', '+-');
W = { 'H1/1','PrevE1/1'; 'H1/1','Jump/1'; 'PrevE1/1','Jump/2'; 'Jump/1','JDiv/1'; 'Hd4/1','JDiv/2'; 'JDiv/1','JRnd/1'; 'JRnd/1','JMul/1'; 'Hd4/1','JMul/2'; ...
      'JMul/1','Nsum/1'; 'Nd/1','Nsum/2'; 'Nsum/1','Nd/1'; 'H1/1','DSum/1'; 'Nsum/1','DSum/2'; 'DSum/1','d/1'};
for k = 1:size(W, 1), ln(s, W{k,1}, W{k,2}); end
% --- wheel-speed sensor: true speed + noise, sampled at 10 Hz
add(s, 'simulink/Sources/Random Number', 'WsNoise', 'Mean', '0', 'Variance', '0.0025', 'Seed', '7', 'SampleTime', '0.1');
add(s, 'simulink/Math Operations/Sum', 'WsSum', 'Inputs', '++');
add(s, 'simulink/Discrete/Zero-Order Hold', 'WsZoh', 'SampleTime', '0.1');
W = { 'vx/1','WsSum/1'; 'WsNoise/1','WsSum/2'; 'WsSum/1','WsZoh/1'; 'WsZoh/1','vmeas/1'};
for k = 1:size(W, 1), ln(s, W{k,1}, W{k,2}); end
try, Simulink.BlockDiagram.arrangeSystem(s); catch, end
end

%% ===================================================================== perception (3 radars x 6 detections)
function buildPerc(g)
s = newSub(g, 'Perception', {'RF', 'RR', 'RS', 'kappa', 'vmeas'}, {'areq', 'occ'});
BS = 'simulink/Signal Routing/Bus Selector';  SEL = 'simulink/Signal Routing/Selector';
buildCand(s);
% zone length ahead on the right: the distance we need to stop plus a margin   xf = v^2/8 + 10
add(s, 'simulink/Math Operations/Product', 'V2', 'Inputs', '**');
add(s, 'simulink/Math Operations/Gain', 'V2g', 'Gain', '0.125');
add(s, 'simulink/Sources/Constant', 'Ten', 'Value', '10');
add(s, 'simulink/Math Operations/Sum', 'XF', 'Inputs', '++');
W = { 'vmeas/1','V2/1'; 'vmeas/1','V2/2'; 'V2/1','V2g/1'; 'V2g/1','XF/1'; 'Ten/1','XF/2'};
for k = 1:size(W, 1), ln(s, W{k,1}, W{k,2}); end
K = 6;  rn = {'RF', 'RR', 'RS'};
add(s, 'simulink/Math Operations/MinMax', 'AMax', 'Function', 'max', 'Inputs', num2str(3*K));
add(s, 'simulink/Logic and Bit Operations/Logical Operator', 'OccOr', 'Operator', 'OR', 'Inputs', num2str(3*K));
n = 0;
for r = 1:3
    bs = sprintf('BS%d', r);
    add(s, BS, bs, 'OutputSignals', 'Detections,NumDetections');
    ln(s, [rn{r} '/1'], [bs '/1']);
    for k = 1:K
        n = n + 1;  tag = sprintf('%d_%d', r, k);
        add(s, SEL, ['S' tag], 'IndexMode', 'One-based', 'NumberOfDimensions', '1', 'InputPortWidth', '-1', 'IndexOptionArray', {'Index vector (dialog)'}, 'IndexParamArray', {num2str(k)});
        add(s, BS, ['M' tag], 'OutputSignals', 'Measurement');
        add(s, 'simulink/Math Operations/Reshape', ['R' tag], 'OutputDimensionality', '1-D array');
        add(s, 'simulink/Signal Routing/Demux', ['D' tag], 'Outputs', '6');
        add(s, 'simulink/Logic and Bit Operations/Compare To Constant', ['V' tag], 'relop', '>=', 'const', num2str(k));
        add_block([s '/Cand'], [s '/C' tag]);
        L = { [bs '/1'], ['S' tag '/1']; ['S' tag '/1'], ['M' tag '/1']; ['M' tag '/1'], ['R' tag '/1']; ['R' tag '/1'], ['D' tag '/1']; ...
              [bs '/2'], ['V' tag '/1']; ...
              ['D' tag '/1'], ['C' tag '/1']; ['D' tag '/2'], ['C' tag '/2']; ['D' tag '/4'], ['C' tag '/3']; ['D' tag '/5'], ['C' tag '/4']; ...
              ['V' tag '/1'], ['C' tag '/5']; 'kappa/1', ['C' tag '/6']; 'vmeas/1', ['C' tag '/7']; 'XF/1', ['C' tag '/8']; ...
              ['C' tag '/1'], sprintf('AMax/%d', n); ['C' tag '/2'], sprintf('OccOr/%d', n)};
        for q = 1:size(L, 1), ln(s, L{q,1}, L{q,2}); end
    end
end
delete_block([s '/Cand']);
ln(s, 'AMax/1', 'areq/1');  ln(s, 'OccOr/1', 'occ/1');
end

function buildCand(p)
% One radar detection -> (a) deceleration needed to avoid it IF it is on my path, (b) is it on the right side where I want to go.
%   Inputs  x y vx vy (ego Cartesian, velocities relative to the ego), v (detection exists), kap (road curvature), vm (speed), xf (zone length)
s = newSub(p, 'Cand', {'x', 'y', 'vx', 'vy', 'v', 'kap', 'vm', 'xf'}, {'areq', 'occ'});
P = 'simulink/Math Operations/Product';  S = 'simulink/Math Operations/Sum';  G = 'simulink/Math Operations/Gain';
C = 'simulink/Logic and Bit Operations/Compare To Constant';  A = 'simulink/Logic and Bit Operations/Logical Operator';
SAT = 'simulink/Discontinuities/Saturation';  R = 'simulink/Logic and Bit Operations/Relational Operator';
% --- path check: lateral position relative to my (curved) path at the object's range, predicted to the time I reach it
add(s, P, 'X2', 'Inputs', '**');  add(s, P, 'KX2', 'Inputs', '**');  add(s, G, 'Half', 'Gain', '0.5');  add(s, S, 'YP', 'Inputs', '+-');
add(s, SAT, 'VmS', 'UpperLimit', 'inf', 'LowerLimit', '1');
add(s, P, 'Tm', 'Inputs', '*/');  add(s, P, 'VyT', 'Inputs', '**');  add(s, S, 'YPred', 'Inputs', '++');
add(s, 'simulink/Math Operations/Abs', 'AbsY');  add(s, C, 'InW', 'relop', '<', 'const', 'ca_hw');
add(s, C, 'XPos', 'relop', '>', 'const', '0.5');  add(s, A, 'InPath', 'Operator', 'AND', 'Inputs', '3');
% --- closing speed: radar velocity relative to the ego (ca_absvel = 1 if the radar reports ground speed instead: then the ego speed is subtracted)
add(s, 'simulink/Sources/Constant', 'AbsK', 'Value', 'ca_absvel');  add(s, P, 'AbsVm', 'Inputs', '**');  add(s, S, 'VxRel', 'Inputs', '+-');
% --- deceleration needed to stop short of it:  vclose^2 / (2 (x - d0))
add(s, G, 'NegVx', 'Gain', '-1');  add(s, SAT, 'Vc', 'UpperLimit', 'inf', 'LowerLimit', '0');
add(s, P, 'Vc2', 'Inputs', '**');
add(s, 'simulink/Sources/Constant', 'D0', 'Value', 'ca_d0');  add(s, S, 'Dx', 'Inputs', '+-');  add(s, SAT, 'DxS', 'UpperLimit', 'inf', 'LowerLimit', '0.5');
add(s, P, 'Areq0', 'Inputs', '*/');  add(s, G, 'HalfA', 'Gain', '0.5');
add(s, 'simulink/Sources/Constant', 'Zero', 'Value', '0');  add(s, 'simulink/Signal Routing/Switch', 'ASw', 'Criteria', 'u2 ~= 0');
% --- right side occupied (lateral position measured from my CURVED path, so a car straight ahead on a bend is not 'on the right'): between my path and the road edge, from behind (closing speed dependent) to the stopping zone ahead
add(s, C, 'YR1', 'relop', '<', 'const', '-0.9');  add(s, C, 'YR2', 'relop', '>', 'const', '-ca_clear+0.2');
add(s, R, 'XL', 'Operator', '<');
add(s, SAT, 'VxP', 'UpperLimit', 'inf', 'LowerLimit', '0');  add(s, G, 'G3', 'Gain', '3');
add(s, 'simulink/Sources/Constant', 'B12', 'Value', '12');  add(s, S, 'Bsum', 'Inputs', '++');  add(s, G, 'NegB', 'Gain', '-1');
add(s, R, 'XB', 'Operator', '>');
add(s, A, 'Occ', 'Operator', 'AND', 'Inputs', '5');
W = { 'x/1','X2/1'; 'x/1','X2/2'; 'kap/1','KX2/1'; 'X2/1','KX2/2'; 'KX2/1','Half/1'; 'y/1','YP/1'; 'Half/1','YP/2'; ...
      'vm/1','VmS/1'; 'x/1','Tm/1'; 'VmS/1','Tm/2'; 'vy/1','VyT/1'; 'Tm/1','VyT/2'; 'YP/1','YPred/1'; 'VyT/1','YPred/2'; ...
      'YPred/1','AbsY/1'; 'AbsY/1','InW/1'; 'x/1','XPos/1'; 'v/1','InPath/1'; 'XPos/1','InPath/2'; 'InW/1','InPath/3'; ...
      'vm/1','AbsVm/1'; 'AbsK/1','AbsVm/2'; 'vx/1','VxRel/1'; 'AbsVm/1','VxRel/2'; 'VxRel/1','NegVx/1'; 'NegVx/1','Vc/1'; 'Vc/1','Vc2/1'; 'Vc/1','Vc2/2'; 'x/1','Dx/1'; 'D0/1','Dx/2'; 'Dx/1','DxS/1'; ...
      'Vc2/1','Areq0/1'; 'DxS/1','Areq0/2'; 'Areq0/1','HalfA/1'; 'HalfA/1','ASw/1'; 'InPath/1','ASw/2'; 'Zero/1','ASw/3'; 'ASw/1','areq/1'; ...
      'YP/1','YR1/1'; 'YP/1','YR2/1'; 'x/1','XL/1'; 'xf/1','XL/2'; 'VxRel/1','VxP/1'; 'VxP/1','G3/1'; 'G3/1','Bsum/1'; 'B12/1','Bsum/2'; 'Bsum/1','NegB/1'; ...
      'x/1','XB/1'; 'NegB/1','XB/2'; 'v/1','Occ/1'; 'YR1/1','Occ/2'; 'YR2/1','Occ/3'; 'XL/1','Occ/4'; 'XB/1','Occ/5'; 'Occ/1','occ/1'};
for k = 1:size(W, 1), ln(s, W{k,1}, W{k,2}); end
end

%% ===================================================================== decision
function buildDec(g)
% Brake demand from the worst obstacle (a car or a pedestrian on my path); move right if there is room and the right side is free.
s = newSub(g, 'Decision', {'areq', 'occ', 'vmeas', 'go'}, {'ulat', 'adem', 'act', 'yshT', 'commit'});
add(s, 'simulink/Signal Attributes/Data Type Conversion', 'Active', 'OutDataTypeStr', 'boolean');   % take-over request from the CabinGuard layer
add(s, 'simulink/Sources/Constant', 'Clear', 'Value', 'ca_clear');
add(s, 'simulink/Sources/Constant', 'Edge', 'Value', 'ca_edge');
add(s, 'simulink/Math Operations/Sum', 'YshT', 'Inputs', '+-');
add(s, 'simulink/Logic and Bit Operations/Compare To Constant', 'Space', 'relop', '>=', 'const', 'ca_min_shift');
add(s, 'simulink/Logic and Bit Operations/Logical Operator', 'NotOcc', 'Operator', 'NOT');
add(s, 'simulink/Logic and Bit Operations/Logical Operator', 'Go', 'Operator', 'AND', 'Inputs', '4');
% feasibility: the sideways move has to fit into the time left to stop:  shift <= k * v_lat * v / a_brake
add(s, 'simulink/Math Operations/Gain', 'FeasK', 'Gain', 'ca_kfeas*ca_vlat');
add(s, 'simulink/Math Operations/Product', 'FeasDiv', 'Inputs', '*/');
add(s, 'simulink/Logic and Bit Operations/Relational Operator', 'FeasCmp', 'Operator', '>=');
add(s, 'simulink/Logic and Bit Operations/Logical Operator', 'CommitOr', 'Operator', 'OR', 'Inputs', '2');
add(s, 'simulink/Discrete/Unit Delay', 'CommitD', 'InitialCondition', '0', 'SampleTime', '0.1');
add(s, 'simulink/Signal Attributes/Data Type Conversion', 'CommitDbl', 'OutDataTypeStr', 'double');
add(s, 'simulink/Signal Attributes/Data Type Conversion', 'ActDbl', 'OutDataTypeStr', 'double');
add(s, 'simulink/Math Operations/Product', 'UProd', 'Inputs', '**');
add(s, 'simulink/Math Operations/Gain', 'UNeg', 'Gain', '-1');
add(s, 'simulink/Math Operations/Gain', 'ReqScaled', 'Gain', '1.25');
add(s, 'simulink/Sources/Constant', 'Comf', 'Value', 'ca_a_comf');
add(s, 'simulink/Math Operations/MinMax', 'MaxA', 'Function', 'max', 'Inputs', '2');
add(s, 'simulink/Discontinuities/Saturation', 'SatA', 'UpperLimit', '8.5', 'LowerLimit', '0');
add(s, 'simulink/Math Operations/Gain', 'NegA', 'Gain', '-1');
W = { 'go/1','Active/1'; 'Clear/1','YshT/1'; 'Edge/1','YshT/2'; 'YshT/1','Space/1'; 'occ/1','NotOcc/1'; ...
      'Active/1','Go/1'; 'Space/1','Go/2'; 'NotOcc/1','Go/3'; 'vmeas/1','FeasK/1'; 'FeasK/1','FeasDiv/1'; 'SatA/1','FeasDiv/2'; 'FeasDiv/1','FeasCmp/1'; 'YshT/1','FeasCmp/2'; 'FeasCmp/1','Go/4'; 'Go/1','CommitOr/1'; 'CommitD/1','CommitOr/2'; 'CommitOr/1','CommitD/1'; ...
      'CommitOr/1','CommitDbl/1'; 'CommitDbl/1','UProd/1'; 'YshT/1','UProd/2'; 'UProd/1','UNeg/1'; 'UNeg/1','ulat/1'; ...
      'areq/1','ReqScaled/1'; 'Comf/1','MaxA/1'; 'ReqScaled/1','MaxA/2'; 'MaxA/1','SatA/1'; 'SatA/1','NegA/1'; 'NegA/1','adem/1'; ...
      'Active/1','ActDbl/1'; 'ActDbl/1','act/1'; 'YshT/1','yshT/1'; 'CommitDbl/1','commit/1'};
for k = 1:size(W, 1), ln(s, W{k,1}, W{k,2}); end
try, Simulink.BlockDiagram.arrangeSystem(s); catch, end
end

%% ===================================================================== guidance
function buildGuid(g)
s = newSub(g, 'Guidance', {'adem', 'ulat', 'go'}, {'yref', 'ydot', 'vref', 'aref', 'act', 'actd', 'up', 'lo'});
add(s, 'simulink/Signal Attributes/Data Type Conversion', 'Active', 'OutDataTypeStr', 'boolean');
add(s, 'simulink/Signal Attributes/Data Type Conversion', 'ActD', 'OutDataTypeStr', 'double');
% smooth lateral reference (critically damped 2nd order) and its derivative; input = signed lateral target from the Decision
add(s, 'simulink/Discontinuities/Rate Limiter', 'LatRL', 'RisingSlewLimit', 'ca_vlat', 'FallingSlewLimit', '-ca_vlat');   % the car cannot move sideways faster than this
add(s, 'simulink/Continuous/Transfer Fcn', 'LcY', 'Numerator', 'ca_wn^2', 'Denominator', '[1 2*ca_wn ca_wn^2]');
add(s, 'simulink/Continuous/Transfer Fcn', 'LcYd', 'Numerator', '[ca_wn^2 0]', 'Denominator', '[1 2*ca_wn ca_wn^2]');
% speed profile: requested decel, jerk limited (brake builds up fast, releases gently), integrated to a speed reference
add(s, 'simulink/Sources/Constant', 'AZero', 'Value', '0');
add(s, 'simulink/Signal Routing/Switch', 'ASw', 'Criteria', 'u2 ~= 0');
add(s, 'simulink/Discontinuities/Rate Limiter', 'Jerk', 'RisingSlewLimit', 'ca_jup', 'FallingSlewLimit', '-ca_jdn');
add(s, 'simulink/Continuous/Integrator', 'VRef', 'InitialCondition', 'ca_v0', 'LimitOutput', 'on', 'UpperSaturationLimit', 'inf', 'LowerSaturationLimit', '0');
% Gateway clamp limits: while active  a_dem <= a <= 0 ; otherwise [-6, +2]
add(s, 'simulink/Sources/Constant', 'UpAct', 'Value', '0');
add(s, 'simulink/Sources/Constant', 'UpIdle', 'Value', '2');
add(s, 'simulink/Signal Routing/Switch', 'UpSw', 'Criteria', 'u2 ~= 0');
add(s, 'simulink/Sources/Constant', 'ClampMax', 'Value', 'ca_a_lo');
add(s, 'simulink/Math Operations/MinMax', 'LoMax', 'Function', 'max', 'Inputs', '2');
add(s, 'simulink/Sources/Constant', 'LoIdle', 'Value', '-6');
add(s, 'simulink/Signal Routing/Switch', 'LoSw', 'Criteria', 'u2 ~= 0');
W = { 'go/1','Active/1'; 'Active/1','ActD/1'; 'ulat/1','LatRL/1'; 'LatRL/1','LcY/1'; 'LatRL/1','LcYd/1'; ...
      'adem/1','ASw/1'; 'Active/1','ASw/2'; 'AZero/1','ASw/3'; 'ASw/1','Jerk/1'; 'Jerk/1','VRef/1'; ...
      'UpAct/1','UpSw/1'; 'Active/1','UpSw/2'; 'UpIdle/1','UpSw/3'; ...
      'ClampMax/1','LoMax/1'; 'adem/1','LoMax/2'; 'LoMax/1','LoSw/1'; 'Active/1','LoSw/2'; 'LoIdle/1','LoSw/3'; ...
      'LcY/1','yref/1'; 'LcYd/1','ydot/1'; 'VRef/1','vref/1'; 'Jerk/1','aref/1'; 'Active/1','act/1'; 'ActD/1','actd/1'; 'UpSw/1','up/1'; 'LoSw/1','lo/1'};
for k = 1:size(W, 1), ln(s, W{k,1}, W{k,2}); end
try, Simulink.BlockDiagram.arrangeSystem(s); catch, end
end

%% ===================================================================== control
function buildCtl(g)
s = newSub(g, 'Control', {'d', 'e2', 'kappa', 'vmeas', 'yref', 'ydot', 'vref', 'aref', 'act', 'up', 'lo'}, {'dcmd', 'acmd'});
% ---- steering: Lane Keeping Assist System (MPC) block
add(s, 'mpcadaslib/Lane Keeping Assist System', 'LKA', 'ModelType', 'Use vehicle parameters', 'VehicleMass', '1500', 'VehicleYawInertia', '2500', ...
    'LengthToFront', '1.2', 'LengthToRear', '1.5', 'FrontTireStiffness', '98100', 'RearTireStiffness', '78480', 'InitialLongVel', '15', ...
    'TransportLag', 'ca_lka_lag', 'MinSteering', '-0.1', 'MaxSteering', '0.1', 'Ts', '0.1', 'PredictionHorizon', '10', 'ControllerBehavior', 'ca_lka_beh');
add(s, 'simulink/Discontinuities/Saturation', 'SteerLim', 'UpperLimit', '0.1', 'LowerLimit', '-0.1');
add(s, 'simulink/Math Operations/Sum', 'DevErr', 'Inputs', '+-');
add(s, 'simulink/Discontinuities/Saturation', 'VxeS', 'UpperLimit', 'inf', 'LowerLimit', '2');
add(s, 'simulink/Math Operations/Product', 'YdDivV', 'Inputs', '*/');
add(s, 'simulink/Math Operations/Sum', 'YawErr', 'Inputs', '+-');
add(s, 'simulink/Math Operations/Gain', 'InDev', 'Gain', 'ca_lka_in');
add(s, 'simulink/Math Operations/Gain', 'InYaw', 'Gain', 'ca_lka_in');
add(s, 'simulink/Math Operations/Gain', 'InKap', 'Gain', 'ca_lka_in');
add(s, 'simulink/Discontinuities/Saturation', 'VLka', 'UpperLimit', '40', 'LowerLimit', '1');
add(s, 'simulink/Math Operations/Gain', 'OutSt', 'Gain', 'ca_lka_out');
add(s, 'simulink/Sources/Constant', 'StraightC', 'Value', '0');
add(s, 'simulink/Signal Routing/Switch', 'StSw', 'Criteria', 'u2 >= Threshold', 'Threshold', '0.5');
W = { 'd/1','DevErr/1'; 'yref/1','DevErr/2'; 'DevErr/1','InDev/1'; ...
      'vmeas/1','VxeS/1'; 'ydot/1','YdDivV/1'; 'VxeS/1','YdDivV/2'; 'e2/1','YawErr/1'; 'YdDivV/1','YawErr/2'; 'YawErr/1','InYaw/1'; ...
      'kappa/1','InKap/1'; 'vmeas/1','VLka/1'; ...
      'InKap/1','LKA/1'; 'VLka/1','LKA/2'; 'InDev/1','LKA/3'; 'InYaw/1','LKA/4'; ...
      'LKA/1','OutSt/1'; 'OutSt/1','SteerLim/1'; 'SteerLim/1','StSw/1'; 'vmeas/1','StSw/2'; 'StraightC/1','StSw/3'; 'StSw/1','dcmd/1'};
for k = 1:size(W, 1), ln(s, W{k,1}, W{k,2}); end
% ---- speed: PID Controller block + feed-forward of the profile acceleration, Gateway clamp via Saturation Dynamic
add(s, 'simulink/Math Operations/Sum', 'VErr', 'Inputs', '+-');
add(s, 'simulink/Continuous/PID Controller', 'SpeedPID', 'Controller', 'PI', 'TimeDomain', 'Discrete-time', 'SampleTime', '0.1', ...
    'P', '1.2', 'I', '0.25', 'LimitOutput', 'on', 'UpperSaturationLimit', '2', 'LowerSaturationLimit', '-9', 'AntiWindupMode', 'clamping');
add(s, 'simulink/Math Operations/Sum', 'FF', 'Inputs', '++');
add(s, 'simulink/Discontinuities/Saturation Dynamic', 'GwClamp');
add(s, 'simulink/Logic and Bit Operations/Compare To Constant', 'Slow', 'relop', '<', 'const', '0.3');
add(s, 'simulink/Logic and Bit Operations/Logical Operator', 'HoldAnd', 'Operator', 'AND', 'Inputs', '2');
add(s, 'simulink/Sources/Constant', 'HoldA', 'Value', '-1.5');
add(s, 'simulink/Signal Routing/Switch', 'HoldSw', 'Criteria', 'u2 ~= 0');
W = { 'vref/1','VErr/1'; 'vmeas/1','VErr/2'; 'VErr/1','SpeedPID/1'; 'SpeedPID/1','FF/1'; 'aref/1','FF/2'; ...
      'up/1','GwClamp/1'; 'FF/1','GwClamp/2'; 'lo/1','GwClamp/3'; ...
      'vmeas/1','Slow/1'; 'act/1','HoldAnd/1'; 'Slow/1','HoldAnd/2'; ...
      'HoldA/1','HoldSw/1'; 'HoldAnd/1','HoldSw/2'; 'GwClamp/1','HoldSw/3'; 'HoldSw/1','acmd/1'};
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
