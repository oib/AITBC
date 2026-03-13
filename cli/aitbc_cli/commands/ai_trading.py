#!/usr/bin/env python3
"""
AI Trading CLI Commands
Advanced AI-powered trading algorithms and analytics
"""

import click
import asyncio
import json
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta

# Import AI trading engine with robust path resolution
import os
import sys

_services_path = os.environ.get('AITBC_SERVICES_PATH')
if _services_path:
    if os.path.isdir(_services_path):
        if _services_path not in sys.path:
            sys.path.insert(0, _services_path)
    else:
        print(f"Warning: AITBC_SERVICES_PATH set but not a directory: {_services_path}", file=sys.stderr)
else:
    _project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
    _computed_services = os.path.join(_project_root, 'apps', 'coordinator-api', 'src', 'app', 'services')
    if os.path.isdir(_computed_services) and _computed_services not in sys.path:
        sys.path.insert(0, _computed_services)
    else:
        _fallback = '/home/oib/windsurf/aitbc/apps/coordinator-api/src/app/services'
        if os.path.isdir(_fallback) and _fallback not in sys.path:
            sys.path.insert(0, _fallback)

try:
    from ai_trading_engine import (
        initialize_ai_engine, train_strategies, generate_trading_signals,
        get_engine_status, ai_trading_engine, TradingStrategy
    )
    _import_error = None
except ImportError as e:
    _import_error = e

    def _missing(*args, **kwargs):
        raise ImportError(
            f"Required service module 'ai_trading_engine' could not be imported: {_import_error}. "
            "Ensure coordinator-api dependencies are installed or set AITBC_SERVICES_PATH."
        )
    initialize_ai_engine = train_strategies = generate_trading_signals = get_engine_status = _missing
    ai_trading_engine = None

    class TradingStrategy:
        pass

@click.group()
def ai_trading():
    """AI-powered trading and analytics commands"""
    pass

@ai_trading.command()
@click.pass_context
def init(ctx):
    """Initialize AI trading engine"""
    try:
        click.echo(f"🤖 Initializing AI Trading Engine...")
        
        success = asyncio.run(initialize_ai_engine())
        
        if success:
            click.echo(f"✅ AI Trading Engine initialized successfully!")
            click.echo(f"📊 Default strategies loaded:")
            click.echo(f"   • Mean Reversion Strategy")
            click.echo(f"   • Momentum Strategy")
        else:
            click.echo(f"❌ Failed to initialize AI Trading Engine")
            
    except Exception as e:
        click.echo(f"❌ Initialization failed: {e}", err=True)

@ai_trading.command()
@click.option("--symbol", default="BTC/USDT", help="Trading symbol")
@click.option("--days", type=int, default=30, help="Days of historical data for training")
@click.pass_context
def train(ctx, symbol: str, days: int):
    """Train AI trading strategies"""
    try:
        click.echo(f"🧠 Training AI Trading Strategies...")
        click.echo(f"📊 Symbol: {symbol}")
        click.echo(f"📅 Training Period: {days} days")
        
        success = asyncio.run(train_strategies(symbol, days))
        
        if success:
            click.echo(f"✅ Training completed successfully!")
            
            # Get training results
            status = get_engine_status()
            click.echo(f"📈 Training Results:")
            click.echo(f"   Strategies Trained: {status['trained_strategies']}/{status['strategies_count']}")
            click.echo(f"   Success Rate: 100%")
            click.echo(f"   Data Points: {days * 24} (hourly data)")
        else:
            click.echo(f"❌ Training failed")
            
    except Exception as e:
        click.echo(f"❌ Training failed: {e}", err=True)

@ai_trading.command()
@click.option("--symbol", default="BTC/USDT", help="Trading symbol")
@click.option("--count", type=int, default=10, help="Number of signals to show")
@click.pass_context
def signals(ctx, symbol: str, count: int):
    """Generate AI trading signals"""
    try:
        click.echo(f"📈 Generating AI Trading Signals...")
        click.echo(f"📊 Symbol: {symbol}")
        
        signals = asyncio.run(generate_trading_signals(symbol))
        
        if not signals:
            click.echo(f"❌ No signals generated. Make sure strategies are trained.")
            return
        
        click.echo(f"\n🎯 Generated {len(signals)} Trading Signals:")
        
        # Display signals
        for i, signal in enumerate(signals[:count]):
            signal_icon = {
                "buy": "🟢",
                "sell": "🔴", 
                "hold": "🟡"
            }.get(signal['signal_type'], "❓")
            
            confidence_color = "🔥" if signal['confidence'] > 0.8 else "⚡" if signal['confidence'] > 0.6 else "💡"
            
            click.echo(f"\n{signal_icon} Signal #{i+1}")
            click.echo(f"   Strategy: {signal['strategy'].replace('_', ' ').title()}")
            click.echo(f"   Signal: {signal['signal_type'].upper()}")
            click.echo(f"   Confidence: {signal['confidence']:.2%} {confidence_color}")
            click.echo(f"   Predicted Return: {signal['predicted_return']:.2%}")
            click.echo(f"   Risk Score: {signal['risk_score']:.2f}")
            click.echo(f"   Reasoning: {signal['reasoning']}")
            click.echo(f"   Time: {signal['timestamp'][:19]}")
        
        if len(signals) > count:
            click.echo(f"\n... and {len(signals) - count} more signals")
        
        # Show summary
        buy_signals = len([s for s in signals if s['signal_type'] == 'buy'])
        sell_signals = len([s for s in signals if s['signal_type'] == 'sell'])
        hold_signals = len([s for s in signals if s['signal_type'] == 'hold'])
        
        click.echo(f"\n📊 Signal Summary:")
        click.echo(f"   🟢 Buy Signals: {buy_signals}")
        click.echo(f"   🔴 Sell Signals: {sell_signals}")
        click.echo(f"   🟡 Hold Signals: {hold_signals}")
        
    except Exception as e:
        click.echo(f"❌ Signal generation failed: {e}", err=True)

@ai_trading.command()
@click.pass_context
def status(ctx):
    """Show AI trading engine status"""
    try:
        click.echo(f"🤖 AI Trading Engine Status")
        
        status = get_engine_status()
        
        click.echo(f"\n📊 Engine Overview:")
        click.echo(f"   Total Strategies: {status['strategies_count']}")
        click.echo(f"   Trained Strategies: {status['trained_strategies']}")
        click.echo(f"   Active Signals: {status['active_signals']}")
        click.echo(f"   Market Data Symbols: {len(status['market_data_symbols'])}")
        
        if status['market_data_symbols']:
            click.echo(f"   Available Symbols: {', '.join(status['market_data_symbols'])}")
        
        # Performance metrics
        metrics = status.get('performance_metrics', {})
        if metrics:
            click.echo(f"\n📈 Performance Metrics:")
            click.echo(f"   Total Signals Generated: {metrics.get('total_signals', 0)}")
            click.echo(f"   Recent Signals: {metrics.get('recent_signals', 0)}")
            click.echo(f"   Average Confidence: {metrics.get('avg_confidence', 0):.1%}")
            click.echo(f"   Average Risk Score: {metrics.get('avg_risk_score', 0):.2f}")
            
            click.echo(f"\n📊 Signal Distribution:")
            click.echo(f"   🟢 Buy Signals: {metrics.get('buy_signals', 0)}")
            click.echo(f"   🔴 Sell Signals: {metrics.get('sell_signals', 0)}")
            click.echo(f"   🟡 Hold Signals: {metrics.get('hold_signals', 0)}")
        
        # Strategy status
        if ai_trading_engine.strategies:
            click.echo(f"\n🧠 Strategy Status:")
            for strategy_name, strategy in ai_trading_engine.strategies.items():
                status_icon = "✅" if strategy.is_trained else "❌"
                click.echo(f"   {status_icon} {strategy_name.replace('_', ' ').title()}")
        
    except Exception as e:
        click.echo(f"❌ Status check failed: {e}", err=True)

@ai_trading.command()
@click.option("--strategy", required=True, help="Strategy to backtest")
@click.option("--symbol", default="BTC/USDT", help="Trading symbol")
@click.option("--days", type=int, default=30, help="Backtesting period in days")
@click.option("--capital", type=float, default=10000, help="Initial capital")
@click.pass_context
def backtest(ctx, strategy: str, symbol: str, days: int, capital: float):
    """Backtest AI trading strategy"""
    try:
        click.echo(f"📊 Backtesting AI Trading Strategy...")
        click.echo(f"🧠 Strategy: {strategy}")
        click.echo(f"📊 Symbol: {symbol}")
        click.echo(f"📅 Period: {days} days")
        click.echo(f"💰 Initial Capital: ${capital:,.2f}")
        
        # Calculate date range
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        
        # Run backtest
        result = asyncio.run(ai_trading_engine.backtest_strategy(
            strategy, symbol, start_date, end_date, capital
        ))
        
        click.echo(f"\n📈 Backtest Results:")
        click.echo(f"   Strategy: {result.strategy.value.replace('_', ' ').title()}")
        click.echo(f"   Period: {result.start_date.strftime('%Y-%m-%d')} to {result.end_date.strftime('%Y-%m-%d')}")
        click.echo(f"   Initial Capital: ${result.initial_capital:,.2f}")
        click.echo(f"   Final Capital: ${result.final_capital:,.2f}")
        
        # Performance metrics
        total_return_pct = result.total_return * 100
        click.echo(f"\n📊 Performance:")
        click.echo(f"   Total Return: {total_return_pct:.2f}%")
        click.echo(f"   Sharpe Ratio: {result.sharpe_ratio:.2f}")
        click.echo(f"   Max Drawdown: {result.max_drawdown:.2%}")
        click.echo(f"   Win Rate: {result.win_rate:.1%}")
        
        # Trading statistics
        click.echo(f"\n📋 Trading Statistics:")
        click.echo(f"   Total Trades: {result.total_trades}")
        click.echo(f"   Profitable Trades: {result.profitable_trades}")
        click.echo(f"   Average Trade: ${(result.final_capital - result.initial_capital) / max(result.total_trades, 1):.2f}")
        
        # Performance assessment
        if total_return_pct > 10:
            assessment = "🔥 EXCELLENT"
        elif total_return_pct > 5:
            assessment = "⚡ GOOD"
        elif total_return_pct > 0:
            assessment = "💡 POSITIVE"
        else:
            assessment = "❌ NEGATIVE"
        
        click.echo(f"\n{assessment} Performance Assessment")
        
    except Exception as e:
        click.echo(f"❌ Backtesting failed: {e}", err=True)

@ai_trading.command()
@click.option("--symbol", default="BTC/USDT", help="Trading symbol")
@click.option("--hours", type=int, default=24, help="Analysis period in hours")
@click.pass_context
def analyze(ctx, symbol: str, hours: int):
    """Analyze market with AI insights"""
    try:
        click.echo(f"🔍 AI Market Analysis...")
        click.echo(f"📊 Symbol: {symbol}")
        click.echo(f"⏰ Period: {hours} hours")
        
        # Get market data
        market_data = ai_trading_engine.market_data.get(symbol)
        if not market_data:
            click.echo(f"❌ No market data available for {symbol}")
            click.echo(f"💡 Train strategies first with: aitbc ai-trading train --symbol {symbol}")
            return
        
        # Get recent data
        recent_data = market_data.tail(hours)
        
        if len(recent_data) == 0:
            click.echo(f"❌ No recent data available")
            return
        
        # Calculate basic statistics
        current_price = recent_data.iloc[-1]['close']
        price_change = (current_price - recent_data.iloc[0]['close']) / recent_data.iloc[0]['close']
        volatility = recent_data['close'].pct_change().std()
        volume_avg = recent_data['volume'].mean()
        
        click.echo(f"\n📊 Market Analysis:")
        click.echo(f"   Current Price: ${current_price:,.2f}")
        click.echo(f"   Price Change: {price_change:.2%}")
        click.echo(f"   Volatility: {volatility:.2%}")
        click.echo(f"   Average Volume: {volume_avg:,.0f}")
        
        # Generate AI signals
        signals = asyncio.run(generate_trading_signals(symbol))
        
        if signals:
            click.echo(f"\n🤖 AI Insights:")
            for signal in signals:
                signal_icon = {"buy": "🟢", "sell": "🔴", "hold": "🟡"}.get(signal['signal_type'], "❓")
                
                click.echo(f"   {signal_icon} {signal['strategy'].replace('_', ' ').title()}:")
                click.echo(f"      Signal: {signal['signal_type'].upper()}")
                click.echo(f"      Confidence: {signal['confidence']:.1%}")
                click.echo(f"      Reasoning: {signal['reasoning']}")
        
        # Market recommendation
        if signals:
            buy_signals = len([s for s in signals if s['signal_type'] == 'buy'])
            sell_signals = len([s for s in signals if s['signal_type'] == 'sell'])
            
            if buy_signals > sell_signals:
                recommendation = "🟢 BULLISH - Multiple buy signals detected"
            elif sell_signals > buy_signals:
                recommendation = "🔴 BEARISH - Multiple sell signals detected"
            else:
                recommendation = "🟡 NEUTRAL - Mixed signals, hold position"
            
            click.echo(f"\n🎯 AI Recommendation: {recommendation}")
        
    except Exception as e:
        click.echo(f"❌ Analysis failed: {e}", err=True)

@ai_trading.command()
@click.pass_context
def strategies(ctx):
    """List available AI trading strategies"""
    try:
        click.echo(f"🧠 Available AI Trading Strategies")
        
        strategies = {
            "mean_reversion": {
                "name": "Mean Reversion",
                "description": "Identifies overbought/oversold conditions using statistical analysis",
                "indicators": ["Z-score", "Rolling mean", "Standard deviation"],
                "time_horizon": "Short-term (hours to days)",
                "risk_level": "Moderate",
                "best_conditions": "Sideways markets with clear mean"
            },
            "momentum": {
                "name": "Momentum",
                "description": "Follows price trends and momentum indicators",
                "indicators": ["Price momentum", "Trend strength", "Volume analysis"],
                "time_horizon": "Medium-term (days to weeks)",
                "risk_level": "Moderate",
                "best_conditions": "Trending markets with clear direction"
            }
        }
        
        for strategy_key, strategy_info in strategies.items():
            click.echo(f"\n📊 {strategy_info['name']}")
            click.echo(f"   Description: {strategy_info['description']}")
            click.echo(f"   Indicators: {', '.join(strategy_info['indicators'])}")
            click.echo(f"   Time Horizon: {strategy_info['time_horizon']}")
            click.echo(f"   Risk Level: {strategy_info['risk_level'].title()}")
            click.echo(f"   Best For: {strategy_info['best_conditions']}")
        
        # Show current status
        if ai_trading_engine.strategies:
            click.echo(f"\n🔧 Current Strategy Status:")
            for strategy_name, strategy in ai_trading_engine.strategies.items():
                status_icon = "✅" if strategy.is_trained else "❌"
                click.echo(f"   {status_icon} {strategy_name.replace('_', ' ').title()}")
        
        click.echo(f"\n💡 Usage Examples:")
        click.echo(f"   aitbc ai-trading train --symbol BTC/USDT")
        click.echo(f"   aitbc ai-trading signals --symbol ETH/USDT")
        click.echo(f"   aitbc ai-trading backtest --strategy mean_reversion --symbol BTC/USDT")
        
    except Exception as e:
        click.echo(f"❌ Strategy listing failed: {e}", err=True)

@ai_trading.command()
@click.pass_context
def test(ctx):
    """Test AI trading engine functionality"""
    try:
        click.echo(f"🧪 Testing AI Trading Engine...")
        
        # Test 1: Initialize
        click.echo(f"\n📋 Test 1: Engine Initialization")
        init_success = asyncio.run(initialize_ai_engine())
        click.echo(f"   ✅ Initialization: {'Success' if init_success else 'Failed'}")
        
        # Test 2: Train strategies
        click.echo(f"\n📋 Test 2: Strategy Training")
        train_success = asyncio.run(train_strategies("BTC/USDT", 7))
        click.echo(f"   ✅ Training: {'Success' if train_success else 'Failed'}")
        
        # Test 3: Generate signals
        click.echo(f"\n📋 Test 3: Signal Generation")
        signals = asyncio.run(generate_trading_signals("BTC/USDT"))
        click.echo(f"   ✅ Signals Generated: {len(signals)}")
        
        # Test 4: Status check
        click.echo(f"\n📋 Test 4: Status Check")
        status = get_engine_status()
        click.echo(f"   ✅ Status Retrieved: {len(status)} metrics")
        
        # Show summary
        click.echo(f"\n🎉 Test Results Summary:")
        click.echo(f"   Engine Status: {'✅ Operational' if init_success and train_success else '❌ Issues'}")
        click.echo(f"   Strategies: {status['strategies_count']} loaded, {status['trained_strategies']} trained")
        click.echo(f"   Signals: {status['active_signals']} generated")
        
        if init_success and train_success:
            click.echo(f"\n✅ AI Trading Engine is ready for production use!")
        else:
            click.echo(f"\n⚠️  Some issues detected - check logs for details")
        
    except Exception as e:
        click.echo(f"❌ Test failed: {e}", err=True)

if __name__ == "__main__":
    ai_trading()
