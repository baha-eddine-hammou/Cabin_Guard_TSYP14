function cg_auto_system(m)
% CG_AUTO_SYSTEM  Adds the CabinGuard layer to CabinGuardAuto (called by cg_auto_build).
%   Detector (surrogate of the AI) -> Faults -> Host (fusion, verification, MRM state machine)
%   -> Gateway (authenticated command boundary) -> take-over request "go" -> GNC (Decision + Guidance)
%   Driver (conscious / syncope / seizure) -> Host (steering torque, grip, pedal)
%   Host -> Telem (e-call over cellular, then SMS)
%   ca_sys = 1 : the take-over starts when the Gateway has accepted the phase  ca_go_phase  (3 = BRAKE)
%   ca_sys = 0 : the take-over starts at the fixed time ca_t_act (old tests)
here = fileparts(mfilename('fullpath'));
s = [m '/CabinGuard'];
try
    buildLayer(m, s, here);
    fprintf('CabinGuard layer: added\n');
    ok = true;
catch e
    fprintf('\n[warn] CabinGuard layer NOT added: %s\n       The model works with the fixed take-over time only.\n', e.message);
    try, delete_block(s); catch, end
    ok = false;  assignin('base', 'ca_sys', 0);
end
% take-over request: timer or CabinGuard layer
add(m, 'simulink/Sources/Clock', 'TClk');
add(m, 'simulink/Logic and Bit Operations/Compare To Constant', 'TimerGo', 'relop', '>=', 'const', 'ca_t_act');
add(m, 'simulink/Sources/Constant', 'SysSel', 'Value', 'ca_sys');
add(m, 'simulink/Signal Routing/Switch', 'SelGo', 'Criteria', 'u2 ~= 0');
ln(m, 'TClk/1', 'TimerGo/1');  ln(m, 'SysSel/1', 'SelGo/2');  ln(m, 'TimerGo/1', 'SelGo/3');
if ok
    ln(m, 'Vehicle/4', 'CabinGuard/1');  ln(m, 'CabinGuard/1', 'SelGo/1');
else
    ln(m, 'TimerGo/1', 'SelGo/1');
end
ln(m, 'SelGo/1', 'GNC/6');
end

function buildLayer(m, s, here)
add_block('simulink/Ports & Subsystems/Subsystem', s);
delete_line(s, 'In1/1', 'Out1/1');  delete_block([s '/In1']);  delete_block([s '/Out1']);
add_block('simulink/Sources/In1', [s '/v'], 'Port', '1');
add_block('simulink/Sinks/Out1', [s '/go'], 'Port', '1');

add(s, 'simulink/Sources/Digital Clock', 'Clk', 'SampleTime', '0.01');
add(s, 'simulink/Discrete/Zero-Order Hold', 'Vz', 'SampleTime', '0.01');
add(s, 'simulink/Sources/Constant', 'PV', 'Value', 'ca_pv(:)');
add(s, 'simulink/Sources/Constant', 'DP', 'Value', 'ca_det(:)');
add(s, 'simulink/Sources/Constant', 'Zero', 'Value', '0');

mfn(s, 'Det',  'cg_sys_detector.m', here, 3, 1);
mfn(s, 'Flt',  'cg_sys_faults.m',   here, 3, 5);
mfn(s, 'Drv',  'cg_sys_driver.m',   here, 5, 6);
mfn(s, 'Host', 'cg_sys_host.m',     here, 9, 9);
mfn(s, 'Gw',   'cg_sys_gateway.m',  here, 5, 8);
mfn(s, 'Tel',  'cg_sys_telem.m',    here, 6, 1);

add(s, 'simulink/Logic and Bit Operations/Compare To Constant', 'GoCmp', 'relop', '>=', 'const', 'ca_go_phase');
add(s, 'simulink/Signal Attributes/Data Type Conversion', 'GoD', 'OutDataTypeStr', 'double');
for nm = {'T1', 'T2', 'T3', 'T4', 'T5', 'T6'}, add(s, 'simulink/Sinks/Terminator', nm{1}); end
add(s, 'simulink/Signal Routing/Mux', 'LogMux', 'Inputs', '18');
add(s, 'simulink/Sinks/To Workspace', 'SysLog', 'VariableName', 'syslog', 'SaveFormat', 'Array', 'SampleTime', '0.02', 'MaxDataPoints', 'inf');

W = { 'v/1','Vz/1'; ...
      'Clk/1','Det/1'; 'PV/1','Det/2'; 'DP/1','Det/3'; ...
      'Clk/1','Flt/1'; 'Det/1','Flt/2'; 'PV/1','Flt/3'; ...
      'Clk/1','Drv/1'; 'Zero/1','Drv/2'; 'Zero/1','Drv/3'; 'Vz/1','Drv/4'; 'PV/1','Drv/5'; ...
      'Clk/1','Host/1'; 'Flt/1','Host/2'; 'Flt/2','Host/3'; 'Drv/3','Host/4'; 'Drv/6','Host/5'; 'Drv/5','Host/6'; 'Drv/4','Host/7'; 'Vz/1','Host/8'; 'PV/1','Host/9'; ...
      'Clk/1','Gw/1'; 'Host/1','Gw/2'; 'Flt/3','Gw/3'; 'Vz/1','Gw/4'; 'PV/1','Gw/5'; ...
      'Clk/1','Tel/1'; 'Host/7','Tel/2'; 'Host/6','Tel/3'; 'Host/5','Tel/4'; 'Flt/4','Tel/5'; 'Flt/5','Tel/6'; ...
      'Gw/2','GoCmp/1'; 'GoCmp/1','go/1'; 'GoCmp/1','GoD/1'; ...
      'Drv/1','T1/1'; 'Drv/2','T2/1'; 'Host/2','T3/1'; 'Gw/3','T4/1'; 'Gw/4','T5/1'; 'Gw/5','T6/1'};
for k = 1:size(W, 1), ln(s, W{k,1}, W{k,2}); end
% log: t, host state, gateway phase, go, alert, ecall, delivered, reject, nrej, alive_lost, dmode, Pmax, cls, warn, a_mrm, tau, pedal, grip
L = { 'Clk/1'; 'Host/9'; 'Gw/2'; 'GoD/1'; 'Host/3'; 'Host/7'; 'Tel/1'; 'Gw/7'; 'Gw/8'; 'Gw/6'; 'Host/4'; 'Host/5'; 'Host/6'; 'Host/8'; 'Gw/1'; 'Drv/3'; 'Drv/4'; 'Drv/6' };
for k = 1:numel(L), ln(s, L{k}, sprintf('LogMux/%d', k)); end
ln(s, 'LogMux/1', 'SysLog/1');
try, Simulink.BlockDiagram.arrangeSystem(s); catch, end
end

function mfn(sys, name, file, here, nin, nout)
% MATLAB Function block with the code of a file (the function name of the file is renamed to fcn)
b = [sys '/' name];
add_block('simulink/User-Defined Functions/MATLAB Function', b);
code = fileread(fullfile(here, file));
code = regexprep(code, '(function[^\n=]*=\s*)cg_sys_\w+', '$1fcn', 'once');
ch = [];
rt = sfroot;
cs = rt.find('-isa', 'Stateflow.EMChart');
for k = 1:numel(cs)
    if strcmp(cs(k).Path, b), ch = cs(k); break, end
end
if isempty(ch), error('Could not find the chart of %s', b); end
ch.Script = code;
try, ch.ChartUpdate = 'DISCRETE';  ch.SampleTime = '0.01'; catch, end
ph = get_param(b, 'PortHandles');
if numel(ph.Inport) ~= nin || numel(ph.Outport) ~= nout
    error('%s: expected %d inputs / %d outputs, found %d / %d', name, nin, nout, numel(ph.Inport), numel(ph.Outport));
end
end

function b = add(sys, lib, name, varargin)
b = [sys '/' name];
add_block(lib, b);
for k = 1:2:numel(varargin)
    try
        set_param(b, varargin{k}, varargin{k+1});
    catch e
        fprintf('  [warn] %s: could not set %s (%s)\n', b, varargin{k}, strtok(e.message, newline));
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
