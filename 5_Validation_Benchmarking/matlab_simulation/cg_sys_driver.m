function [steer, a_drv, tau, brake_pedal, clonic, grip] = cg_sys_driver(t, y, psi, v, pv)
% DRIVER + INCAPACITATION INJECTOR (kinematic-bicycle driver model)
%   outputs: steer (rad, front wheel), a_drv (m/s2 traction demand), tau (Nm, wheel torque),
%            brake_pedal (0/1), clonic (0/1, from motion features), grip (0 active, 1 off, 2 clenched)
L = 2.7;  wn = 0.8;  zt = 0.9;
t_on = pv(1);  ev = pv(2);  v0 = pv(3);  t_can = pv(10);  tonic = pv(14);
vs = max(v, 5);
drag = 0.5*1.2*0.7*v^2/1500 + 0.012*9.81;
% conscious driver: lane keeping + speed hold
steer = -(wn^2*L/vs^2)*y - (2*zt*wn*L/vs)*psi;
a_drv = min(2, max(-3, drag + 0.5*(v0 - v)));
tau = 1.5 + 20*abs(steer);
brake_pedal = 0;  clonic = 0;  grip = 0;

% conscious driver answering a false alarm
if ev == 0 && t_can > 0 && t >= t_can
    brake_pedal = 1;  tau = 6;  a_drv = -1.5;
end

if ev ~= 0 && t >= t_on
    te = t - t_on;
    if ev == 1                      % syncope: flaccid, hands off, pedal released
        steer = 0;  a_drv = 0;  tau = 0;  grip = 1;
    else                            % seizure
        if te < tonic               % tonic: clenched grip, wheel pushed, pedal held
            steer = 0.01;  a_drv = drag;  tau = 8;  grip = 2;
        else                        % clonic: 4 Hz jerking on wheel and pedal
            ph = 2*pi*4*(te - tonic);
            steer = 0.01 + 0.015*sin(ph);
            a_drv = drag + 1.0*sin(ph);
            tau = 8*sin(ph);
            clonic = 1;  grip = 2;
        end
    end
end
steer = max(-0.1, min(0.1, steer));
end

