function cg_auto_plant(m)
% CG_AUTO_PLANT  Adds the detailed longitudinal plant (Vehicle Dynamics Blockset) to the Vehicle subsystem of CabinGuardAuto.
%   Called by cg_auto_build. After it, the speed of the car can come from either plant (base variable ca_plant):
%       ca_plant = 1 : Vehicle Body 3DOF Longitudinal (mass, drag, pitch / load transfer) + 2 x Longitudinal Wheel - Disc Brake
%                      (Magic Formula slip force, wheel spin, brake torque) + brake line (0.12 s hydraulic lag, 65/35 balance,
%                      feed-forward pressure + trim on the measured deceleration) + drive torque (0.15 s lag)
%       ca_plant = 0 : the simple plant (first-order acceleration lag, saturation at -mu g)
%   The lateral part (bicycle model with friction-limited tyre force) is the same in both.
%   Self-calibrating: it checks how the body reports the axle loads, how it scales the wheel force, and the
%   brake pressure unit, and prints all of it.
load_system('autolibshared');  load_system('vehdynlibtire');
par = struct('m',1500,'a',1.2,'b',1.5,'h',0.55,'mu',0.9,'Re',0.31,'Iyy',2800,'Iw',1.0, ...
             'CdA',0.7,'T',293,'crr',0.012,'bias',0.65,'tauP',0.12,'tauD',0.15);
par.L = par.a + par.b;
par.lbRef = 'autolibshared/Vehicle Body 3DOF Longitudinal';
par.wRef  = 'vehdynlibtire/Longitudinal Wheel - Disc Brake';
fprintf('Detailed plant: calibrating the Vehicle Dynamics Blockset blocks ...\n');
cfg = calibrate_long(par);
fprintf('Calibration: Fz scale %.2f, force scale %.3f, pressure unit scale %g, decel per front pressure %.3e (m/s^2)/unit\n', ...
    cfg.cz, cfg.kF, cfg.pu, cfg.Keff);

s = [m '/Vehicle'];
add_long_core(s, par, cfg, 'ca_v0');
add = @(lib, name, varargin) add_block(lib, [s '/' name], varargin{:});
SUM = 'simulink/Math Operations/Sum';  GAIN = 'simulink/Math Operations/Gain';
INT = 'simulink/Continuous/Integrator';  SAT = 'simulink/Discontinuities/Saturation';
SW = 'simulink/Signal Routing/Switch';  CONST = 'simulink/Sources/Constant';
TF = 'simulink/Continuous/Transfer Fcn';
Pmax = 150e5*cfg.pu;
add(GAIN, 'BrkReq0', 'Gain', '-1');
add(SAT, 'BrkReq', 'UpperLimit', '10', 'LowerLimit', '0');
add(TF, 'AMeas', 'Numerator', '[1 0]', 'Denominator', '[0.15 1]');
add(SUM, 'TrimErr', 'Inputs', '++');
add('simulink/Logic and Bit Operations/Compare To Constant', 'NotBrk', 'relop', '<', 'const', '0.05');
add(INT, 'Trim', 'InitialCondition', '0', 'LimitOutput', 'on', 'UpperSaturationLimit', '3', ...
    'LowerSaturationLimit', '-3', 'ExternalReset', 'level');
add(GAIN, 'TrimK', 'Gain', '0.4');                 % softer feedback trim: less chatter of the measured deceleration
add(SUM, 'ReqSum', 'Inputs', '++');
add(GAIN, 'ToPrs', 'Gain', num2str(1/cfg.Keff, 10));
add(SAT, 'PrsSat', 'UpperLimit', num2str(Pmax, 10), 'LowerLimit', '0');
add(CONST, 'PmaxC', 'Value', num2str(Pmax, 10));
add(SW, 'ParkPrs', 'Threshold', '0.5', 'Criteria', 'u2 >= Threshold');
add(SUM, 'PErr', 'Inputs', '+-');
add(GAIN, 'PLagK', 'Gain', num2str(1/par.tauP, 10));
add(INT, 'PInt', 'InitialCondition', '0', 'LimitOutput', 'on', 'UpperSaturationLimit', num2str(Pmax, 10), 'LowerSaturationLimit', '0');
add(SAT, 'DrvSat', 'UpperLimit', '5', 'LowerLimit', '0');
add(GAIN, 'DrvK', 'Gain', num2str(par.m*par.Re/2, 10));
add(TF, 'DrvLag', 'Numerator', '1', 'Denominator', ['[' num2str([par.tauD 1]) ']']);
add(SAT, 'SatV', 'UpperLimit', 'inf', 'LowerLimit', '0');
% hold at standstill: full brake pressure when the car is (almost) stopped and still asked to brake
add('simulink/Logic and Bit Operations/Compare To Constant', 'SlowC', 'relop', '<', 'const', '0.4');
add('simulink/Logic and Bit Operations/Compare To Constant', 'BrkC', 'relop', '<', 'const', '-0.05');
add('simulink/Logic and Bit Operations/Logical Operator', 'ParkAnd', 'Operator', 'AND', 'Inputs', '2');
add('simulink/Signal Attributes/Data Type Conversion', 'park', 'OutDataTypeStr', 'double');

% standstill hold: the planner's braking request (park) goes to the body
if ~(isfield(par, 'body') && strcmp(par.body, 'vdbs'))
    lhb = get_param([s '/LBody'], 'LineHandles');
    if lhb.Inport(5) > 0, delete_line(lhb.Inport(5)); end
    delete_block([s '/HoldZ']);
end
% the simple plant fed VxHi; now the detailed plant feeds it
lh = get_param([s '/VxHi'], 'LineHandles');
if lh.Inport(1) > 0, delete_line(lh.Inport(1)); end

W = {'acmd/1','BrkReq0/1'; 'BrkReq0/1','BrkReq/1'; 'acmd/1','DrvSat/1'; ...
     'VxOut/1','AMeas/1'; 'BrkReq/1','TrimErr/1'; 'AMeas/1','TrimErr/2'; ...
     'BrkReq/1','NotBrk/1'; 'TrimErr/1','TrimK/1'; 'TrimK/1','Trim/1'; 'NotBrk/1','Trim/2'; ...
     'BrkReq/1','ReqSum/1'; 'Trim/1','ReqSum/2'; 'ReqSum/1','ToPrs/1'; 'ToPrs/1','PrsSat/1'; ...
     'VxOut/1','SlowC/1'; 'acmd/1','BrkC/1'; 'SlowC/1','ParkAnd/1'; 'BrkC/1','ParkAnd/2'; 'ParkAnd/1','park/1'; ...
     'PmaxC/1','ParkPrs/1'; 'park/1','ParkPrs/2'; 'PrsSat/1','ParkPrs/3'; ...
     'ParkPrs/1','PErr/1'; 'PInt/1','PErr/2'; 'PErr/1','PLagK/1'; 'PLagK/1','PInt/1'; 'PInt/1','PfIn/1'; ...
     'DrvSat/1','DrvK/1'; 'DrvK/1','DrvLag/1'; 'DrvLag/1','TqIn/1'; ...
     'VxOut/1','SatV/1'; 'SatV/1','VxHi/1'};
if ~(isfield(par, 'body') && strcmp(par.body, 'vdbs')), W(end+1, :) = {'park/1', 'LBody/5'}; end
for k = 1:size(W,1), ensure_line(s, W{k,1}, W{k,2}); end
fprintf('Detailed plant added to %s (select with ca_plant = 1, simple plant = 0).\n', s);
end

% ---------------------------------------------------------------------------------------------
function add_long_core(s, par, cfg, v0str)
% Body + two wheels + force/Fz plumbing. Entry blocks: PfIn (front wheel brake pressure), TqIn (rear wheel
% axle torque). Exit block: VxOut (body speed).
add = @(lib, name, varargin) add_block(lib, [s '/' name], varargin{:});
GAIN = 'simulink/Math Operations/Gain';  SUM = 'simulink/Math Operations/Sum';
CONST = 'simulink/Sources/Constant';  SW = 'simulink/Signal Routing/Switch';
if isfield(par, 'body') && strcmp(par.body, 'vdbs')
    bd = [s '/LBody'];  add_block(par.lbRef, bd);
    setp(bd, {'groundType','Grade angle'; 'm',par.m; 'a',par.a; 'b',par.b; 'h',par.h; 'Cd',0.32; 'Af',par.CdA/0.32; ...
              'Cl',0; 'Cpm',0; 'Iyy',par.Iyy; 'T',par.T; 'NF',2; 'NR',2; 'xdot_o',v0str});
else
    add_body_simple(s, par, v0str);     % rigid body with load transfer, built from basic blocks (see add_body_simple)
end
for nm = {'WF','WR'}
    w = [s '/' nm{1}];  add_block(par.wRef, w);
    setp(w, {'BrakeType','Disc'; 'vertType','None'; 'rollingType','None'; 'Re',par.Re; 'UNLOADED_RADIUS',par.Re; ...
             'Iyy',par.Iw; 'FNOMIN',4000; 'lam_muV',par.mu; 'omegao',['(' v0str ')/' num2str(par.Re)]});
end
add(GAIN, 'PfIn', 'Gain', '1');  add(GAIN, 'TqIn', 'Gain', '1');  add(GAIN, 'VxOut', 'Gain', '1');
add(GAIN, 'Rb', 'Gain', num2str((1-par.bias)/par.bias, 10));
add(CONST, 'ZeroT', 'Value', '0');
add(GAIN, 'CzF', 'Gain', num2str(cfg.cz));  add(GAIN, 'CzR', 'Gain', num2str(cfg.cz));
add('simulink/Discrete/Unit Delay', 'DlyF', 'SampleTime', '0.01', 'InitialCondition', num2str(par.m*9.81*par.b/par.L/2, 10));
add('simulink/Discrete/Unit Delay', 'DlyR', 'SampleTime', '0.01', 'InitialCondition', num2str(par.m*9.81*par.a/par.L/2, 10));
add(GAIN, 'KFf', 'Gain', num2str(cfg.kF, 10));  add(GAIN, 'KFr', 'Gain', num2str(cfg.kF, 10));
add(SUM, 'FwFSum', 'Inputs', '++');  add(SUM, 'FwRSum', 'Inputs', '++');
Fr = par.crr*par.m*9.81;
add(CONST, 'RollC', 'Value', num2str(-Fr, 10));  add(CONST, 'RollZ', 'Value', '0');
add(SW, 'RollSw', 'Threshold', '0.1', 'Criteria', 'u2 >= Threshold');
add(GAIN, 'RollGF', 'Gain', num2str(par.b/par.L, 10));  add(GAIN, 'RollGR', 'Gain', num2str(par.a/par.L, 10));
add(CONST, 'GradeC', 'Value', '0');  add(CONST, 'WindC', 'Value', '[0 0 0]');
ownBody = ~(isfield(par, 'body') && strcmp(par.body, 'vdbs'));
if ownBody, add(CONST, 'HoldZ', 'Value', '0'); end
for k = 1:5, add('simulink/Sinks/Terminator', sprintf('TL%d', k)); end
W = {'LBody/2','VxOut/1'; 'PfIn/1','WF/1'; 'PfIn/1','Rb/1'; 'Rb/1','WR/1'; ...
     'ZeroT/1','WF/2'; 'TqIn/1','WR/2'; 'VxOut/1','WF/3'; 'VxOut/1','WR/3'; ...
     'LBody/3','CzF/1'; 'LBody/4','CzR/1'; 'CzF/1','DlyF/1'; 'CzR/1','DlyR/1'; 'DlyF/1','WF/4'; 'DlyR/1','WR/4'; ...
     'WF/2','KFf/1'; 'WR/2','KFr/1'; ...
     'RollC/1','RollSw/1'; 'VxOut/1','RollSw/2'; 'RollZ/1','RollSw/3'; 'RollSw/1','RollGF/1'; 'RollSw/1','RollGR/1'; ...
     'KFf/1','FwFSum/1'; 'RollGF/1','FwFSum/2'; 'KFr/1','FwRSum/1'; 'RollGR/1','FwRSum/2'; ...
     'FwFSum/1','LBody/1'; 'FwRSum/1','LBody/2'; 'GradeC/1','LBody/3'; 'WindC/1','LBody/4'; ...
     'LBody/1','TL1/1'; 'WF/1','TL2/1'; 'WR/1','TL3/1'; 'WF/3','TL4/1'; 'WR/3','TL5/1'};
if ownBody, W(end+1, :) = {'HoldZ/1', 'LBody/5'}; end
% NOTE: the body's INPUT ports are FwF, FwR, Grade, WindXYZ (1..4) and its OUTPUT ports Info, xdot, FzF, FzR.
% add_line uses 'Block/n' for output n of the source and input n of the destination, so the table above is
% read as (source output, destination input); the first column of LBody entries below are outputs.
for k = 1:size(W,1)
    ensure_line(s, W{k,1}, W{k,2});
end
end

function add_body_simple(s, par, v0str)
% Longitudinal body from basic blocks, same ports as 'Vehicle Body 3DOF Longitudinal':
%   inputs  FwF, FwR (axle forces, N), Grade, Wind, Hold (0/1)      outputs  Info (0), xdot, FzF, FzR (per wheel, N)
%   m ax = FwF + FwR - 0.5 rho CdA v^2                            speed = integral of ax, not below 0
%   load transfer: FzF = (m g b - m h ax)/(2 L),  FzR = (m g a + m h ax)/(2 L)  (per wheel), ax filtered by a first-order lag
%   (tau 0.15 s = pitch response of the suspension). Why not the Vehicle Dynamics Blockset body: its default suspension (bump stop of
%   about 2 MN/m, damping about 300 N s/m) rings at 9 Hz and my table changes had no effect on it.
%   Standstill hold: below 0.4 m/s and with the hold request (input 5: the planner asks for braking) the speed decays to 0 with a 0.05 s time constant
%   (the wheel block alone leaves a creep of about 0.2 m/s at rest).
b = [s '/LBody'];
add_block('simulink/Ports & Subsystems/Subsystem', b);
Simulink.SubSystem.deleteContents(b);
ad = @(lib, name, varargin) add_block(lib, [b '/' name], varargin{:});
ln = @(a, c) add_line(b, a, c, 'autorouting', 'on');
ad('simulink/Sources/In1', 'FwF', 'Port', '1');  ad('simulink/Sources/In1', 'FwR', 'Port', '2');
ad('simulink/Sources/In1', 'Grade', 'Port', '3');  ad('simulink/Sources/In1', 'Wind', 'Port', '4');  ad('simulink/Sources/In1', 'HoldIn', 'Port', '5');
ad('simulink/Sinks/Out1', 'Info', 'Port', '1');  ad('simulink/Sinks/Out1', 'xdot', 'Port', '2');
ad('simulink/Sinks/Out1', 'FzF', 'Port', '3');  ad('simulink/Sinks/Out1', 'FzR', 'Port', '4');
ad('simulink/Sinks/Terminator', 'TG');  ad('simulink/Sinks/Terminator', 'TW');
ad('simulink/Sources/Constant', 'Z', 'Value', '0');
ad('simulink/Math Operations/Sum', 'Fsum', 'Inputs', '++');
ad('simulink/Math Operations/Product', 'V2', 'Inputs', '2');
ad('simulink/Math Operations/Gain', 'Kd', 'Gain', num2str(0.5*1.205*par.CdA, 10));
ad('simulink/Math Operations/Sum', 'Net', 'Inputs', '+-');
ad('simulink/Math Operations/Gain', 'InvM', 'Gain', num2str(1/par.m, 10));
ad('simulink/Math Operations/Gain', 'Hold', 'Gain', '-20');
ad('simulink/Logic and Bit Operations/Compare To Constant', 'Slow', 'relop', '<', 'const', '0.4');
ad('simulink/Logic and Bit Operations/Compare To Constant', 'Brk', 'relop', '>', 'const', '0.5');   % hold request from outside (brake demanded)
ad('simulink/Logic and Bit Operations/Logical Operator', 'HAnd', 'Operator', 'AND', 'Inputs', '2');
ad('simulink/Signal Routing/Switch', 'HSw', 'Criteria', 'u2 ~= 0');
ad('simulink/Continuous/Integrator', 'Ix', 'InitialCondition', v0str, 'LimitOutput', 'on', 'UpperSaturationLimit', 'inf', 'LowerSaturationLimit', '0');
ad('simulink/Continuous/Transfer Fcn', 'Pitch', 'Numerator', '1', 'Denominator', '[0.15 1]');
ad('simulink/Math Operations/Gain', 'KhF', 'Gain', num2str(-par.m*par.h/(2*par.L), 10));
ad('simulink/Math Operations/Gain', 'KhR', 'Gain', num2str(par.m*par.h/(2*par.L), 10));
ad('simulink/Sources/Constant', 'CF', 'Value', num2str(par.m*9.81*par.b/(2*par.L), 10));
ad('simulink/Sources/Constant', 'CR', 'Value', num2str(par.m*9.81*par.a/(2*par.L), 10));
ad('simulink/Math Operations/Sum', 'SF', 'Inputs', '++');  ad('simulink/Math Operations/Sum', 'SR', 'Inputs', '++');
L = {'FwF/1','Fsum/1'; 'FwR/1','Fsum/2'; 'Grade/1','TG/1'; 'Wind/1','TW/1'; 'Z/1','Info/1'; ...
     'Ix/1','V2/1'; 'Ix/1','V2/2'; 'V2/1','Kd/1'; 'Fsum/1','Net/1'; 'Kd/1','Net/2'; 'Net/1','InvM/1'; ...
     'Ix/1','Hold/1'; 'Ix/1','Slow/1'; 'HoldIn/1','Brk/1'; 'Slow/1','HAnd/1'; 'Brk/1','HAnd/2'; ...
     'Hold/1','HSw/1'; 'HAnd/1','HSw/2'; 'InvM/1','HSw/3'; 'HSw/1','Ix/1'; 'Ix/1','xdot/1'; ...
     'InvM/1','Pitch/1'; 'Pitch/1','KhF/1'; 'Pitch/1','KhR/1'; 'KhF/1','SF/1'; 'CF/1','SF/2'; 'KhR/1','SR/1'; 'CR/1','SR/2'; ...
     'SF/1','FzF/1'; 'SR/1','FzR/1'};
for k = 1:size(L, 1), ln(L{k,1}, L{k,2}); end
end

function setp(b, p)
for i = 1:size(p,1)
    v = p{i,2};  if isnumeric(v), v = num2str(v, 10); end
    try, set_param(b, p{i,1}, v);
    catch ME, warning('  could not set %s on %s: %s', p{i,1}, get_param(b,'Name'), strtok(ME.message, newline)); end
end
end

function ensure_line(s, src, dst)
% add_line unless the destination port is already connected to something
[db, dp] = strtok(dst, '/');  dp = str2double(dp(2:end));
lh = get_param([s '/' db], 'LineHandles');
if numel(lh.Inport) >= dp && lh.Inport(dp) > 0
    srcPort = get_param(lh.Inport(dp), 'SrcPortHandle');
    if srcPort > 0, return, end
end
add_line(s, src, dst, 'autorouting', 'on');
end

function cfg = calibrate_long(par)
cfg = struct('cz', 0.5, 'kF', 2, 'pu', 1, 'Keff', 1e-6);
v0 = 20;  mg = par.m*9.81;
% (1) what do FzF, FzR mean? coast with no brake and compare the sum with m g
o = run_cal(par, cfg, v0, 0, 5);
n = o.t > 3;
sumFz = mean(o.FzF(n) + o.FzR(n));
c = 0.5*mg/sumFz;
fprintf('  FzF+FzR = %.0f N (m g = %.0f N) -> per-wheel scale %.3f\n', sumFz, mg, c);
ac = (interp1(o.t, o.vx, 3) - interp1(o.t, o.vx, 5))/2;  vc = mean(o.vx(o.t > 3));
fprintf('  coasting decel %.3f m/s^2 at %.1f m/s; aero %.3f + rolling %.3f = %.3f expected\n', ac, vc, ...
    0.5*1.205*par.CdA*vc^2/par.m, par.crr*9.81, 0.5*1.205*par.CdA*vc^2/par.m + par.crr*9.81);
if abs(c - 0.5) < 0.05, cfg.cz = 0.5; elseif abs(c - 1) < 0.1, cfg.cz = 1;
else, error('FzF+FzR = %.0f N is neither m g nor m g/2 (%.0f N). Send me this line and the previous output.', sumFz, mg); end
% (2)-(4) brake step: front pressure P0, rear by the bias
for attempt = 1:2
    if attempt == 1, P0 = 20e5; cfg.pu = 1; else, P0 = 20; cfg.pu = 1e-5; end
    o = run_cal(par, cfg, v0, P0, 5);
    a = (interp1(o.t, o.vx, 2.0) - interp1(o.t, o.vx, 3.0));            % decel, m/s^2
    fprintf('  brake step %.3g: decel %.3f m/s^2 at about %.0f m/s\n', P0, a, mean(o.vx(o.t > 2 & o.t < 3)));
    if a > 0.3, break, end
end
if a <= 0.3, error('The wheels produce no braking (decel %.3f). Send me the lines above.', a); end
vm = mean(o.vx(o.t > 2 & o.t < 3));
Fdrag = 0.5*1.205*par.CdA*vm^2;  Fr = par.crr*mg;
Fnet = par.m*a - Fdrag - Fr;                                              % force the wheels produced (N)
Fwh = -2*(mean(o.FxF(o.t > 2 & o.t < 3)) + mean(o.FxR(o.t > 2 & o.t < 3)));  % what 2 wheels per axle should give
r = Fnet/Fwh;
fprintf('  net braking force %.0f N, two wheels per axle would give %.0f N -> body applies %.2f x my scaling\n', Fnet, Fwh, r);
% The force scale is 2 (two wheels per axle). The full-braking check in the main function confirms it
% (force ratio = kF/2). The low-pressure ratio above is informational only.
cfg.kF = 2;
cfg.Keff = Fwh/par.m/P0;                                                 % decel per unit FRONT pressure, from the wheel forces
if cfg.Keff <= 0 || ~isfinite(cfg.Keff), error('Keff = %g, calibration failed.', cfg.Keff); end
% (5) confirm with the corrected scaling
o = run_cal(par, cfg, v0, P0, 5);
a2 = interp1(o.t, o.vx, 2.0) - interp1(o.t, o.vx, 3.0);
fprintf('  with corrected scaling: decel %.3f m/s^2 (predicted %.3f)\n', a2, cfg.Keff*P0 + (Fdrag + Fr)/par.m);
end

function o = run_cal(par, cfg, v0, P0, T)
mdl = 'cg_cal_long';
if bdIsLoaded(mdl), close_system(mdl, 0); end
new_system(mdl);
add_long_core(mdl, par, cfg, num2str(v0));
add_block('simulink/Sources/Step', [mdl '/P'], 'Time', '1', 'Before', '0', 'After', num2str(P0, 10));
add_block('simulink/Sources/Constant', [mdl '/Q'], 'Value', '0');
add_line(mdl, 'P/1', 'PfIn/1');  add_line(mdl, 'Q/1', 'TqIn/1');
sig = {'vx','LBody/2'; 'FzF','LBody/3'; 'FzR','LBody/4'; 'FxF','WF/2'; 'FxR','WR/2'};
for i = 1:size(sig,1)
    add_block('simulink/Sinks/To Workspace', [mdl '/L' sig{i,1}], 'VariableName', ['log_' sig{i,1}], 'SaveFormat', 'Array');
    add_line(mdl, sig{i,2}, ['L' sig{i,1} '/1'], 'autorouting', 'on');   % branches off the existing line
end
set_param(mdl, 'SolverType', 'Fixed-step', 'Solver', 'ode4', 'FixedStep', '0.01', 'StopTime', num2str(T));
out = sim(mdl);
o.t = out.tout(:);
for i = 1:size(sig,1), o.(sig{i,1}) = out.(['log_' sig{i,1}])(:); end
close_system(mdl, 0);
end

