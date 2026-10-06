// toast.js
import React from 'react';
import { toast } from 'react-toastify';
import { CheckCircle, XCircle, AlertCircle, Info, Zap } from 'lucide-react';

// Base toast styling with glassmorphism
const baseToastClasses = [
  '!bg-slate-900/70',
  'backdrop-blur-xl',
  'backdrop-saturate-[180%]',
  '!border',
  '!rounded-2xl',
  '!text-white',
  '!p-4',
  '!min-h-[64px]',
  '!font-sans',
  '!shadow-[0_8px_32px_rgba(0,0,0,0.4),0_0_0_1px_rgba(139,92,246,0.1),inset_0_1px_0_rgba(255,255,255,0.1)]',
  'hover:!translate-y-[-2px]',
  'hover:!scale-[1.02]',
  'hover:!shadow-[0_12px_40px_rgba(0,0,0,0.5),0_0_0_1px_rgba(139,92,246,0.2),inset_0_1px_0_rgba(255,255,255,0.15)]',
  'transition-all',
  'duration-200',
  'ease-out'
].join(' ');

// Success variant
const successClasses = [
  baseToastClasses,
  '!border-purple-500/30',
  '!bg-gradient-to-br',
  'from-purple-500/15',
  'to-slate-900/70'
].join(' ');

// Error variant
const errorClasses = [
  baseToastClasses,
  '!border-red-500/30',
  '!bg-gradient-to-br',
  'from-red-500/15',
  'to-slate-900/70'
].join(' ');

// Info variant
const infoClasses = [
  baseToastClasses,
  '!border-blue-500/30',
  '!bg-gradient-to-br',
  'from-blue-500/15',
  'to-slate-900/70'
].join(' ');

// Warning variant
const warningClasses = [
  baseToastClasses,
  '!border-amber-400/30',
  '!bg-gradient-to-br',
  'from-amber-400/15',
  'to-slate-900/70'
].join(' ');

// Body styling
const bodyClasses = [
  '!p-0',
  '!text-sm',
  '!font-medium',
  '!leading-6',
  '!text-white/95'
].join(' ');

// Progress bar variants
const progressSuccess = [
  '!bg-gradient-to-r',
  'from-purple-500/80',
  'to-purple-400',
  '!h-[3px]',
  '!rounded-b-2xl',
  '!shadow-[0_0_10px_rgba(139,92,246,0.5)]'
].join(' ');

const progressError = [
  '!bg-gradient-to-r',
  'from-red-500/80',
  'to-red-400',
  '!h-[3px]',
  '!rounded-b-2xl',
  '!shadow-[0_0_10px_rgba(239,68,68,0.5)]'
].join(' ');

const progressInfo = [
  '!bg-gradient-to-r',
  'from-blue-500/80',
  'to-blue-400',
  '!h-[3px]',
  '!rounded-b-2xl',
  '!shadow-[0_0_10px_rgba(59,130,246,0.5)]'
].join(' ');

const progressWarning = [
  '!bg-gradient-to-r',
  'from-amber-400/80',
  'to-amber-400',
  '!h-[3px]',
  '!rounded-b-2xl',
  '!shadow-[0_0_10px_rgba(251,191,36,0.5)]'
].join(' ');

// Icon classes
const iconSuccess = 'w-5 h-5 text-purple-400 drop-shadow-[0_0_8px_rgba(167,139,250,0.8)]';
const iconError = 'w-5 h-5 text-red-400 drop-shadow-[0_0_8px_rgba(248,113,113,0.8)]';
const iconInfo = 'w-5 h-5 text-blue-400 drop-shadow-[0_0_8px_rgba(96,165,250,0.8)]';
const iconWarning = 'w-5 h-5 text-amber-400 drop-shadow-[0_0_8px_rgba(251,191,36,0.8)]';

// Default configuration - ALL TOASTS AT TOP-RIGHT
const defaultConfig = {
  position: "top-right",
  autoClose: 5000,
  hideProgressBar: false,
  closeOnClick: true,
  pauseOnHover: true,
  draggable: true,
  theme: "dark",
  bodyClassName: bodyClasses,
};

// Toast notification functions
export const showToast = {
  // All regular alerts appear at TOP-RIGHT
  success: (message) => {
    toast.success(message, {
      ...defaultConfig,
      icon: () => React.createElement(CheckCircle, { className: iconSuccess }),
      className: successClasses,
      progressClassName: progressSuccess,
    });
  },
  
  error: (message) => {
    toast.error(message, {
      ...defaultConfig,
      icon: () => React.createElement(XCircle, { className: iconError }),
      className: errorClasses,
      progressClassName: progressError,
    });
  },
  
  info: (message, extra = {}) => {
    toast.info(message, {
      ...defaultConfig,
      autoClose: 3000,
      icon: () => React.createElement(Info, { className: iconInfo }),
      className: infoClasses,
      progressClassName: progressInfo,
      ...extra,
    });
  },
  
  warning: (message) => {
    toast.warning(message, {
      ...defaultConfig,
      autoClose: 4000,
      icon: () => React.createElement(AlertCircle, { className: iconWarning }),
      className: warningClasses,
      progressClassName: progressWarning,
    });
  },

  successLong: (message) => {
    toast.success(message, {
      ...defaultConfig,
      autoClose: 7000,
      icon: () => React.createElement(Zap, { className: iconSuccess }),
      className: successClasses,
      progressClassName: progressSuccess,
    });
  },

  successBottom: (message) => {
    toast.success(message, {
      ...defaultConfig,
      position: "bottom-right",
      autoClose: 3000,
      icon: () => React.createElement(CheckCircle, { className: iconSuccess }),
      className: successClasses,
      progressClassName: progressSuccess,
    });
  },

  // ONLY for video generation - appears at TOP-CENTER
  infoCenter: (message) => {
    toast.info(message, {
      ...defaultConfig,
      position: "top-center",
      autoClose: 3000,
      icon: () => React.createElement(Info, { className: iconInfo }),
      className: infoClasses,
      progressClassName: progressInfo,
    });
  },

  // Bonus: Additional helpful variants
  promise: (promise, messages) => {
    return toast.promise(
      promise,
      {
        pending: {
          render: messages.pending || 'Loading...',
          icon: () => React.createElement(Info, { className: iconInfo }),
          className: infoClasses,
        },
        success: {
          render: messages.success || 'Success!',
          icon: () => React.createElement(CheckCircle, { className: iconSuccess }),
          className: successClasses,
          progressClassName: progressSuccess,
        },
        error: {
          render: messages.error || 'Error occurred',
          icon: () => React.createElement(XCircle, { className: iconError }),
          className: errorClasses,
          progressClassName: progressError,
        }
      },
      {
        ...defaultConfig,
        bodyClassName: bodyClasses,
      }
    );
  },

  custom: (message, options = {}) => {
    toast(message, {
      ...defaultConfig,
      ...options,
      className: successClasses,
      progressClassName: progressSuccess,
    });
  }
};

// Container configuration for your ToastContainer component
export const toastContainerConfig = {
  position: "top-right",
  autoClose: 5000,
  hideProgressBar: false,
  newestOnTop: true,
  closeOnClick: true,
  rtl: false,
  pauseOnFocusLoss: true,
  draggable: true,
  pauseOnHover: true,
  theme: "dark",
  className: "!p-4",
  toastClassName: "!mb-3",
  limit: 5,
};
