# Activation Tracking Integration Examples

This document provides practical examples of how to integrate the activation tracking system into SignalixAI components.

## 1. Risk Profiling Wizard Integration

**Component**: `signalixai-frontend/components/auth/RiskProfilingWizard.tsx`

```typescript
import { trackRiskProfileSaved } from '@/lib/analytics/activation';
import { useAuth } from '@/stores/auth';

export function RiskProfilingWizard() {
  const { user } = useAuth();
  
  const handleSubmit = async (formData: RiskProfileData) => {
    try {
      // Save profile to backend
      const response = await fetch('/api/user/risk-profile', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(formData),
      });
      
      if (!response.ok) {
        throw new Error('Failed to save risk profile');
      }
      
      // Track activation event
      if (user?.id) {
        await trackRiskProfileSaved(user.id, {
          experience: formData.experience,
          markets: formData.markets,
          capital: formData.capital,
        });
      }
      
      // Redirect to dashboard
      router.push('/dashboard?welcome=true');
      
    } catch (error) {
      console.error('Error saving risk profile:', error);
      toast.error('Failed to save risk profile');
    }
  };
  
  return (
    <form onSubmit={handleSubmit}>
      {/* Form fields */}
    </form>
  );
}
```

## 2. Watchlist Manager Integration

**Component**: `signalixai-frontend/components/watchlist/WatchlistManager.tsx`

```typescript
import { trackWatchlistAdded } from '@/lib/analytics/activation';
import { useAuth } from '@/stores/auth';
import { useWatchlist } from '@/hooks/useWatchlist';

export function WatchlistManager() {
  const { user } = useAuth();
  const { watchlist, addInstrument } = useWatchlist();
  
  const handleAddInstrument = async (instrument: Instrument) => {
    try {
      // Add to watchlist
      await addInstrument(instrument);
      
      // Get updated count
      const newCount = watchlist.length + 1;
      
      // Track activation event (only fires when count >= 3)
      if (user?.id) {
        await trackWatchlistAdded(user.id, newCount);
      }
      
      toast.success(`Added ${instrument.symbol} to watchlist`);
      
    } catch (error) {
      console.error('Error adding instrument:', error);
      toast.error('Failed to add instrument');
    }
  };
  
  return (
    <div>
      <InstrumentSearch onSelect={handleAddInstrument} />
      <WatchlistTable instruments={watchlist} />
    </div>
  );
}
```

## 3. Analysis Runner Integration

**Component**: `signalixai-frontend/components/analysis/AnalysisRunner.tsx`

```typescript
import { trackFirstAnalysisRun } from '@/lib/analytics/activation';
import { useAuth } from '@/stores/auth';

export function AnalysisRunner() {
  const { user } = useAuth();
  const [hasRunAnalysis, setHasRunAnalysis] = useState(false);
  
  const handleRunAnalysis = async (instrument: Instrument) => {
    try {
      // Run analysis
      const response = await fetch('/api/analysis/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          instrument: instrument.symbol,
          analysisType: 'full',
        }),
      });
      
      if (!response.ok) {
        throw new Error('Analysis failed');
      }
      
      const result = await response.json();
      
      // Track first analysis (only once)
      if (user?.id && !hasRunAnalysis) {
        await trackFirstAnalysisRun(user.id, {
          instrument: instrument.symbol,
          analysisType: 'full',
        });
        setHasRunAnalysis(true);
      }
      
      // Show results
      router.push(`/dashboard/analysis/${result.id}`);
      
    } catch (error) {
      console.error('Error running analysis:', error);
      toast.error('Failed to run analysis');
    }
  };
  
  return (
    <button onClick={() => handleRunAnalysis(selectedInstrument)}>
      Run Analysis
    </button>
  );
}
```

## 4. Signal Detail View Integration

**Component**: `signalixai-frontend/components/signals/SignalDetail.tsx`

```typescript
import { trackFirstSignalViewed } from '@/lib/analytics/activation';
import { useAuth } from '@/stores/auth';
import { useEffect, useState } from 'react';

export function SignalDetail({ signalId }: { signalId: string }) {
  const { user } = useAuth();
  const [signal, setSignal] = useState<Signal | null>(null);
  const [hasViewedSignal, setHasViewedSignal] = useState(false);
  
  useEffect(() => {
    const loadSignal = async () => {
      try {
        const response = await fetch(`/api/signals/${signalId}`);
        const data = await response.json();
        setSignal(data);
        
        // Track first signal view (only once)
        if (user?.id && !hasViewedSignal) {
          await trackFirstSignalViewed(user.id, {
            signalId: data.id,
            instrument: data.instrument,
            recommendation: data.recommendation,
          });
          setHasViewedSignal(true);
        }
        
      } catch (error) {
        console.error('Error loading signal:', error);
      }
    };
    
    loadSignal();
  }, [signalId, user?.id, hasViewedSignal]);
  
  if (!signal) return <LoadingSpinner />;
  
  return (
    <div>
      <h1>{signal.instrument} - {signal.recommendation}</h1>
      {/* Signal details */}
    </div>
  );
}
```

## 5. Onboarding Checklist Integration

**Component**: `signalixai-frontend/components/dashboard/OnboardingChecklist.tsx`

```typescript
import { getActivationStatus, ActivationEventType } from '@/lib/analytics/activation';
import { useAuth } from '@/stores/auth';
import { useEffect, useState } from 'react';

export function OnboardingChecklist() {
  const { user } = useAuth();
  const [status, setStatus] = useState<ActivationStatus | null>(null);
  
  useEffect(() => {
    const loadStatus = async () => {
      if (user?.id) {
        const activationStatus = await getActivationStatus(user.id);
        setStatus(activationStatus);
      }
    };
    
    loadStatus();
    
    // Refresh every 30 seconds
    const interval = setInterval(loadStatus, 30000);
    return () => clearInterval(interval);
  }, [user?.id]);
  
  if (!status) return null;
  
  const checklistItems = [
    {
      id: 'profile',
      title: 'Complete your profile',
      completed: status.completedEvents.includes(ActivationEventType.RISK_PROFILE_SAVED),
      href: '/dashboard/settings/profile',
    },
    {
      id: 'watchlist',
      title: 'Add 3+ instruments to watchlist',
      completed: status.completedEvents.includes(ActivationEventType.WATCHLIST_ADDED),
      href: '/dashboard/watchlist',
    },
    {
      id: 'analysis',
      title: 'Run your first analysis',
      completed: status.completedEvents.includes(ActivationEventType.FIRST_ANALYSIS_RUN),
      href: '/dashboard/analysis',
    },
    {
      id: 'signal',
      title: 'View signal details',
      completed: status.completedEvents.includes(ActivationEventType.FIRST_SIGNAL_VIEWED),
      href: '/dashboard/signals',
    },
  ];
  
  const completedCount = checklistItems.filter(item => item.completed).length;
  const progress = (completedCount / checklistItems.length) * 100;
  
  // Show celebration if just completed
  useEffect(() => {
    if (status.isActivated && progress === 100) {
      // Show confetti animation
      confetti({
        particleCount: 100,
        spread: 70,
        origin: { y: 0.6 }
      });
      
      toast.success('🎉 Congratulations! You\'ve completed onboarding!');
    }
  }, [status.isActivated, progress]);
  
  return (
    <div className="bg-white rounded-lg shadow p-6">
      <h2 className="text-xl font-semibold mb-4">Get Started</h2>
      
      <div className="mb-4">
        <div className="flex justify-between text-sm mb-2">
          <span>{completedCount} of {checklistItems.length} complete</span>
          <span>{Math.round(progress)}%</span>
        </div>
        <div className="w-full bg-gray-200 rounded-full h-2">
          <div 
            className="bg-blue-600 h-2 rounded-full transition-all duration-500"
            style={{ width: `${progress}%` }}
          />
        </div>
      </div>
      
      <ul className="space-y-3">
        {checklistItems.map(item => (
          <li key={item.id} className="flex items-center">
            <div className={`
              w-6 h-6 rounded-full flex items-center justify-center mr-3
              ${item.completed ? 'bg-green-500' : 'bg-gray-300'}
            `}>
              {item.completed && (
                <svg className="w-4 h-4 text-white" fill="currentColor" viewBox="0 0 20 20">
                  <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
                </svg>
              )}
            </div>
            
            {item.completed ? (
              <span className="text-gray-500 line-through">{item.title}</span>
            ) : (
              <a href={item.href} className="text-blue-600 hover:underline">
                {item.title}
              </a>
            )}
          </li>
        ))}
      </ul>
      
      {status.isActivated && (
        <div className="mt-4 p-3 bg-green-50 border border-green-200 rounded">
          <p className="text-sm text-green-800">
            ✓ You're all set! Completed in {Math.round((status.timeToActivation || 0) / 60)} minutes.
          </p>
        </div>
      )}
    </div>
  );
}
```

## 6. Dashboard Welcome Modal Integration

**Component**: `signalixai-frontend/components/dashboard/WelcomeModal.tsx`

```typescript
import { getActivationStatus } from '@/lib/analytics/activation';
import { useAuth } from '@/stores/auth';
import { useEffect, useState } from 'react';

export function WelcomeModal() {
  const { user } = useAuth();
  const [show, setShow] = useState(false);
  const [status, setStatus] = useState<ActivationStatus | null>(null);
  
  useEffect(() => {
    const checkWelcome = async () => {
      // Show on first dashboard visit
      const hasSeenWelcome = localStorage.getItem('hasSeenWelcome');
      
      if (!hasSeenWelcome && user?.id) {
        setShow(true);
        
        // Load activation status
        const activationStatus = await getActivationStatus(user.id);
        setStatus(activationStatus);
      }
    };
    
    checkWelcome();
  }, [user?.id]);
  
  const handleClose = () => {
    localStorage.setItem('hasSeenWelcome', 'true');
    setShow(false);
  };
  
  if (!show || !status) return null;
  
  const nextStep = status.pendingEvents[0];
  const nextStepText = {
    'risk_profile_saved': 'Complete your profile',
    'watchlist_added': 'Add instruments to watchlist',
    'first_analysis_run': 'Run your first analysis',
    'first_signal_viewed': 'View a signal',
  }[nextStep] || 'Continue exploring';
  
  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div className="bg-white rounded-lg p-8 max-w-md">
        <h2 className="text-2xl font-bold mb-4">Welcome to SignalixAI! 🎉</h2>
        
        <p className="text-gray-600 mb-6">
          Let's get you started with AI-powered trading signals in just a few steps.
        </p>
        
        <div className="space-y-3 mb-6">
          <div className="flex items-center">
            <div className="w-8 h-8 rounded-full bg-blue-100 text-blue-600 flex items-center justify-center mr-3">
              1
            </div>
            <span>Complete your profile</span>
          </div>
          <div className="flex items-center">
            <div className="w-8 h-8 rounded-full bg-blue-100 text-blue-600 flex items-center justify-center mr-3">
              2
            </div>
            <span>Add 3+ instruments to watchlist</span>
          </div>
          <div className="flex items-center">
            <div className="w-8 h-8 rounded-full bg-blue-100 text-blue-600 flex items-center justify-center mr-3">
              3
            </div>
            <span>Run your first analysis</span>
          </div>
        </div>
        
        <button
          onClick={handleClose}
          className="w-full bg-blue-600 text-white py-3 rounded-lg hover:bg-blue-700"
        >
          {nextStepText}
        </button>
      </div>
    </div>
  );
}
```

## 7. Email Trigger Integration

**Backend**: `signalixai-backend/services/marketing-service/app/services/activation_triggers.py`

```python
"""
Activation-based email triggers

Sends behavioral emails based on activation events.
"""

from app.services.email_service import EmailService
from app.routers.activation import ActivationEventType

email_service = EmailService()


async def handle_activation_event(user_id: str, event_type: ActivationEventType):
    """
    Handle activation event and trigger appropriate emails
    """
    
    if event_type == ActivationEventType.RISK_PROFILE_SAVED:
        # Send "Next Steps" email
        await email_service.send_transactional_email(
            template="onboarding_next_steps",
            to_email=user_email,
            context={
                "user_id": user_id,
                "next_step": "Add instruments to your watchlist"
            }
        )
    
    elif event_type == ActivationEventType.WATCHLIST_ADDED:
        # Send "Run First Analysis" email
        await email_service.send_transactional_email(
            template="run_first_analysis",
            to_email=user_email,
            context={
                "user_id": user_id,
                "watchlist_count": 3
            }
        )
    
    elif event_type == ActivationEventType.ACTIVATION_COMPLETED:
        # Send "Congratulations" email
        await email_service.send_transactional_email(
            template="activation_completed",
            to_email=user_email,
            context={
                "user_id": user_id,
                "time_to_activation_minutes": time_to_activation // 60
            }
        )
```

## 8. Analytics Dashboard Integration

**Component**: `signalixai-frontend/components/admin/ActivationMetrics.tsx`

```typescript
import { useEffect, useState } from 'react';

export function ActivationMetrics() {
  const [metrics, setMetrics] = useState({
    activationRate: 0,
    avgTimeToActivation: 0,
    totalActivated: 0,
    totalSignups: 0,
  });
  
  useEffect(() => {
    const loadMetrics = async () => {
      const response = await fetch('/api/admin/activation-metrics');
      const data = await response.json();
      setMetrics(data);
    };
    
    loadMetrics();
    
    // Refresh every minute
    const interval = setInterval(loadMetrics, 60000);
    return () => clearInterval(interval);
  }, []);
  
  return (
    <div className="grid grid-cols-4 gap-4">
      <MetricCard
        title="Activation Rate"
        value={`${metrics.activationRate.toFixed(1)}%`}
        target="50%"
        status={metrics.activationRate >= 50 ? 'good' : 'warning'}
      />
      
      <MetricCard
        title="Avg Time to Activation"
        value={`${Math.round(metrics.avgTimeToActivation / 60)} min`}
        target="<10 min"
        status={metrics.avgTimeToActivation < 600 ? 'good' : 'warning'}
      />
      
      <MetricCard
        title="Activated Users"
        value={metrics.totalActivated.toLocaleString()}
      />
      
      <MetricCard
        title="Total Signups"
        value={metrics.totalSignups.toLocaleString()}
      />
    </div>
  );
}
```

## Testing Integration

### Test in Browser Console

```javascript
// Import functions (if using module)
import {
  trackRiskProfileSaved,
  trackWatchlistAdded,
  trackFirstAnalysisRun,
  trackFirstSignalViewed,
  getActivationStatus
} from '@/lib/analytics/activation';

// Test user ID
const userId = 'test_user_123';

// Track events
await trackRiskProfileSaved(userId, { experience: 'intermediate' });
await trackWatchlistAdded(userId, 3);
await trackFirstAnalysisRun(userId, { instrument: 'NIFTY' });
await trackFirstSignalViewed(userId, { signalId: 'sig_123' });

// Check status
const status = await getActivationStatus(userId);
console.log('Activated:', status.isActivated);
console.log('Time:', status.timeToActivation, 'seconds');
```

## Best Practices

1. **Track Early**: Call tracking functions as soon as the action completes
2. **Handle Errors**: Wrap tracking calls in try-catch to prevent blocking user flow
3. **Check User ID**: Always verify user is authenticated before tracking
4. **Avoid Duplicates**: Use flags or state to prevent multiple tracking calls
5. **Test Thoroughly**: Test activation flow end-to-end before deploying
6. **Monitor Metrics**: Set up alerts for activation rate drops
7. **Iterate**: Use data to optimize onboarding flow

## Common Issues

### Events Not Tracking
- Check user is authenticated
- Verify marketing service is running
- Check browser console for errors
- Verify API routes are working

### Duplicate Events
- Use state flags to track if event already fired
- Check unique constraint is in database
- Review component lifecycle to prevent re-renders

### Activation Not Completing
- Verify all 4 events are tracked
- Check event types match exactly
- Review backend logs for errors
- Test with fresh user account

## Support

For issues or questions:
1. Check `ACTIVATION_TRACKING_README.md` for detailed documentation
2. Review test suite in `test_activation.py`
3. Check backend logs for errors
4. Contact development team
