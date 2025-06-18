# app/langgraph/workflows/workflow_manager.py - LangGraph Workflow Manager
"""
Comprehensive workflow management system for LangGraph workflows.
Handles workflow execution, monitoring, optimization, and lifecycle management.
"""

import logging
import asyncio
from typing import Dict, Any, Optional, List, Callable, Type
from datetime import datetime, timedelta
from enum import Enum
import json
import uuid
from dataclasses import dataclass, field

# LangGraph imports
from langgraph.graph import StateGraph, END
from langgraph.checkpoint import MemorySaver
from langgraph.pregel import Pregel

# Workflow state management
from app.langgraph.state.search_state import SearchState, ProcessingStage

# Performance monitoring
from prometheus_client import Counter, Histogram, Gauge

logger = logging.getLogger(__name__)

# Metrics
WORKFLOW_EXECUTIONS = Counter('workflow_executions_total', 'Total workflow executions', ['workflow_type', 'status'])
WORKFLOW_DURATION = Histogram('workflow_duration_seconds', 'Workflow execution duration', ['workflow_type'])
ACTIVE_WORKFLOWS = Gauge('active_workflows', 'Currently active workflows')
WORKFLOW_ERRORS = Counter('workflow_errors_total', 'Workflow errors', ['workflow_type', 'error_type'])

class WorkflowType(str, Enum):
    """Types of workflows"""
    SIMPLE = "simple"
    ADAPTIVE = "adaptive"
    ITERATIVE = "iterative"
    RESEARCH = "research"
    COLLABORATIVE = "collaborative"
    CUSTOM = "custom"

class WorkflowStatus(str, Enum):
    """Workflow execution status"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMEOUT = "timeout"

class OptimizationLevel(str, Enum):
    """Workflow optimization levels"""
    SPEED = "speed"
    QUALITY = "quality"
    BALANCED = "balanced"
    COST_EFFICIENT = "cost_efficient"

@dataclass
class WorkflowExecution:
    """Workflow execution tracking"""
    execution_id: str
    workflow_type: WorkflowType
    status: WorkflowStatus
    started_at: datetime
    completed_at: Optional[datetime] = None
    duration_seconds: Optional[float] = None
    input_data: Dict[str, Any] = field(default_factory=dict)
    output_data: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    optimization_level: OptimizationLevel = OptimizationLevel.BALANCED
    performance_metrics: Dict[str, Any] = field(default_factory=dict)
    resource_usage: Dict[str, Any] = field(default_factory=dict)
    quality_scores: Dict[str, float] = field(default_factory=dict)

@dataclass
class WorkflowConfig:
    """Workflow configuration"""
    workflow_type: WorkflowType
    timeout_seconds: int = 300
    max_retries: int = 3
    optimization_level: OptimizationLevel = OptimizationLevel.BALANCED
    enable_checkpointing: bool = True
    enable_monitoring: bool = True
    custom_parameters: Dict[str, Any] = field(default_factory=dict)

class WorkflowRegistry:
    """Registry for workflow types and their implementations"""
    
    def __init__(self):
        self._workflows: Dict[WorkflowType, Type] = {}
        self._configs: Dict[WorkflowType, WorkflowConfig] = {}
    
    def register_workflow(self, workflow_type: WorkflowType, 
                         workflow_class: Type, 
                         config: Optional[WorkflowConfig] = None):
        """Register a workflow type"""
        self._workflows[workflow_type] = workflow_class
        self._configs[workflow_type] = config or WorkflowConfig(workflow_type)
        logger.info(f"Registered workflow: {workflow_type.value}")
    
    def get_workflow_class(self, workflow_type: WorkflowType) -> Optional[Type]:
        """Get workflow class by type"""
        return self._workflows.get(workflow_type)
    
    def get_workflow_config(self, workflow_type: WorkflowType) -> Optional[WorkflowConfig]:
        """Get workflow configuration by type"""
        return self._configs.get(workflow_type)
    
    def list_workflows(self) -> List[WorkflowType]:
        """List all registered workflows"""
        return list(self._workflows.keys())

class WorkflowOptimizer:
    """Optimizes workflow execution based on requirements"""
    
    def __init__(self):
        self.optimization_strategies = {
            OptimizationLevel.SPEED: self._speed_optimization,
            OptimizationLevel.QUALITY: self._quality_optimization,
            OptimizationLevel.BALANCED: self._balanced_optimization,
            OptimizationLevel.COST_EFFICIENT: self._cost_optimization
        }
    
    def optimize_workflow_config(self, config: WorkflowConfig, 
                                context: Dict[str, Any]) -> WorkflowConfig:
        """Optimize workflow configuration based on context"""
        strategy = self.optimization_strategies.get(
            config.optimization_level, 
            self._balanced_optimization
        )
        
        return strategy(config, context)
    
    def _speed_optimization(self, config: WorkflowConfig, 
                          context: Dict[str, Any]) -> WorkflowConfig:
        """Optimize for speed"""
        config.timeout_seconds = min(config.timeout_seconds, 60)
        config.custom_parameters.update({
            'max_search_engines': 2,
            'max_content_urls': 5,
            'parallel_processing': True,
            'cache_aggressive': True,
            'skip_optional_steps': True
        })
        return config
    
    def _quality_optimization(self, config: WorkflowConfig, 
                            context: Dict[str, Any]) -> WorkflowConfig:
        """Optimize for quality"""
        config.timeout_seconds = max(config.timeout_seconds, 180)
        config.custom_parameters.update({
            'max_search_engines': 5,
            'max_content_urls': 15,
            'enable_fact_checking': True,
            'enable_source_verification': True,
            'multiple_validation_rounds': True
        })
        return config
    
    def _balanced_optimization(self, config: WorkflowConfig, 
                             context: Dict[str, Any]) -> WorkflowConfig:
        """Balanced optimization"""
        config.custom_parameters.update({
            'max_search_engines': 3,
            'max_content_urls': 10,
            'enable_basic_validation': True,
            'adaptive_timeout': True
        })
        return config
    
    def _cost_optimization(self, config: WorkflowConfig, 
                         context: Dict[str, Any]) -> WorkflowConfig:
        """Optimize for cost efficiency"""
        config.custom_parameters.update({
            'max_search_engines': 1,
            'max_content_urls': 3,
            'use_cheaper_models': True,
            'aggressive_caching': True,
            'minimize_api_calls': True
        })
        return config

class WorkflowMonitor:
    """Monitors workflow execution and performance"""
    
    def __init__(self):
        self.active_executions: Dict[str, WorkflowExecution] = {}
        self.execution_history: List[WorkflowExecution] = []
        self.performance_stats: Dict[str, Any] = {}
    
    def start_execution(self, execution: WorkflowExecution):
        """Start monitoring a workflow execution"""
        self.active_executions[execution.execution_id] = execution
        ACTIVE_WORKFLOWS.inc()
        logger.info(f"Started monitoring workflow: {execution.execution_id}")
    
    def update_execution(self, execution_id: str, updates: Dict[str, Any]):
        """Update execution status and metrics"""
        if execution_id in self.active_executions:
            execution = self.active_executions[execution_id]
            
            for key, value in updates.items():
                if hasattr(execution, key):
                    setattr(execution, key, value)
            
            # Update performance metrics
            if execution.status == WorkflowStatus.COMPLETED:
                if execution.started_at and execution.completed_at:
                    execution.duration_seconds = (
                        execution.completed_at - execution.started_at
                    ).total_seconds()
                    
                    WORKFLOW_DURATION.labels(
                        workflow_type=execution.workflow_type.value
                    ).observe(execution.duration_seconds)
    
    def complete_execution(self, execution_id: str, 
                          status: WorkflowStatus = WorkflowStatus.COMPLETED,
                          output_data: Optional[Dict[str, Any]] = None,
                          error_message: Optional[str] = None):
        """Complete workflow execution monitoring"""
        if execution_id not in self.active_executions:
            return
        
        execution = self.active_executions[execution_id]
        execution.status = status
        execution.completed_at = datetime.utcnow()
        execution.output_data = output_data
        execution.error_message = error_message
        
        if execution.started_at:
            execution.duration_seconds = (
                execution.completed_at - execution.started_at
            ).total_seconds()
        
        # Record metrics
        WORKFLOW_EXECUTIONS.labels(
            workflow_type=execution.workflow_type.value,
            status=status.value
        ).inc()
        
        if status == WorkflowStatus.FAILED and error_message:
            WORKFLOW_ERRORS.labels(
                workflow_type=execution.workflow_type.value,
                error_type=type(error_message).__name__
            ).inc()
        
        if execution.duration_seconds:
            WORKFLOW_DURATION.labels(
                workflow_type=execution.workflow_type.value
            ).observe(execution.duration_seconds)
        
        # Move to history
        self.execution_history.append(execution)
        del self.active_executions[execution_id]
        ACTIVE_WORKFLOWS.dec()
        
        logger.info(f"Completed workflow monitoring: {execution_id} - {status.value}")
    
    def get_execution_stats(self) -> Dict[str, Any]:
        """Get workflow execution statistics"""
        total_executions = len(self.execution_history)
        if total_executions == 0:
            return {}
        
        successful = sum(1 for e in self.execution_history if e.status == WorkflowStatus.COMPLETED)
        failed = sum(1 for e in self.execution_history if e.status == WorkflowStatus.FAILED)
        
        durations = [e.duration_seconds for e in self.execution_history 
                    if e.duration_seconds is not None]
        
        return {
            'total_executions': total_executions,
            'successful_executions': successful,
            'failed_executions': failed,
            'success_rate': successful / total_executions,
            'active_executions': len(self.active_executions),
            'average_duration': sum(durations) / len(durations) if durations else 0,
            'min_duration': min(durations) if durations else 0,
            'max_duration': max(durations) if durations else 0
        }

class WorkflowManager:
    """Main workflow management system"""
    
    def __init__(self):
        self.registry = WorkflowRegistry()
        self.optimizer = WorkflowOptimizer()
        self.monitor = WorkflowMonitor()
        self.checkpointer = MemorySaver()
        self._setup_default_workflows()
    
    def _setup_default_workflows(self):
        """Setup default workflow registrations"""
        # Import and register default workflows
        try:
            from app.langgraph.workflows.search_workflow import MasterSearchWorkflow
            
            # Register different workflow configurations
            self.registry.register_workflow(
                WorkflowType.SIMPLE,
                MasterSearchWorkflow,
                WorkflowConfig(
                    workflow_type=WorkflowType.SIMPLE,
                    timeout_seconds=60,
                    optimization_level=OptimizationLevel.SPEED
                )
            )
            
            self.registry.register_workflow(
                WorkflowType.ADAPTIVE,
                MasterSearchWorkflow,
                WorkflowConfig(
                    workflow_type=WorkflowType.ADAPTIVE,
                    timeout_seconds=120,
                    optimization_level=OptimizationLevel.BALANCED
                )
            )
            
            self.registry.register_workflow(
                WorkflowType.RESEARCH,
                MasterSearchWorkflow,
                WorkflowConfig(
                    workflow_type=WorkflowType.RESEARCH,
                    timeout_seconds=300,
                    optimization_level=OptimizationLevel.QUALITY
                )
            )
            
        except ImportError as e:
            logger.warning(f"Could not import default workflows: {e}")
    
    async def execute_workflow(self, workflow_type: WorkflowType,
                             input_data: Dict[str, Any],
                             config_overrides: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Execute a workflow with monitoring and optimization"""
        
        execution_id = str(uuid.uuid4())
        
        # Get workflow class and config
        workflow_class = self.registry.get_workflow_class(workflow_type)
        if not workflow_class:
            raise ValueError(f"Unknown workflow type: {workflow_type}")
        
        config = self.registry.get_workflow_config(workflow_type)
        if config_overrides:
            config.custom_parameters.update(config_overrides)
        
        # Optimize configuration
        config = self.optimizer.optimize_workflow_config(config, input_data)
        
        # Create execution tracking
        execution = WorkflowExecution(
            execution_id=execution_id,
            workflow_type=workflow_type,
            status=WorkflowStatus.PENDING,
            started_at=datetime.utcnow(),
            input_data=input_data,
            optimization_level=config.optimization_level
        )
        
        self.monitor.start_execution(execution)
        
        try:
            # Update status to running
            self.monitor.update_execution(execution_id, {'status': WorkflowStatus.RUNNING})
            
            # Create and configure workflow instance
            workflow_instance = workflow_class()
            
            # Apply configuration parameters
            await self._apply_workflow_config(workflow_instance, config)
            
            # Execute workflow with timeout
            result = await asyncio.wait_for(
                self._execute_with_monitoring(workflow_instance, input_data, execution_id),
                timeout=config.timeout_seconds
            )
            
            # Complete monitoring
            self.monitor.complete_execution(
                execution_id,
                WorkflowStatus.COMPLETED,
                result
            )
            
            return result
            
        except asyncio.TimeoutError:
            self.monitor.complete_execution(
                execution_id,
                WorkflowStatus.TIMEOUT,
                error_message="Workflow execution timed out"
            )
            raise TimeoutError(f"Workflow execution timed out after {config.timeout_seconds} seconds")
            
        except Exception as e:
            self.monitor.complete_execution(
                execution_id,
                WorkflowStatus.FAILED,
                error_message=str(e)
            )
            logger.error(f"Workflow execution failed: {e}")
            raise
    
    async def _apply_workflow_config(self, workflow_instance, config: WorkflowConfig):
        """Apply configuration to workflow instance"""
        # Apply custom parameters to workflow
        for param, value in config.custom_parameters.items():
            if hasattr(workflow_instance, param):
                setattr(workflow_instance, param, value)
            elif hasattr(workflow_instance, 'config'):
                workflow_instance.config[param] = value
    
    async def _execute_with_monitoring(self, workflow_instance, 
                                     input_data: Dict[str, Any],
                                     execution_id: str) -> Dict[str, Any]:
        """Execute workflow with detailed monitoring"""
        
        # Create initial state
        if hasattr(workflow_instance, 'create_initial_state'):
            state = workflow_instance.create_initial_state(input_data)
        else:
            # Create default SearchState
            state = SearchState(
                query=input_data.get('query', ''),
                query_id=execution_id,
                user_id=input_data.get('user_id'),
                session_id=input_data.get('session_id'),
                **input_data
            )
        
        # Execute workflow
        if hasattr(workflow_instance, 'workflow') and hasattr(workflow_instance.workflow, 'ainvoke'):
            # LangGraph workflow
            config = {"configurable": {"thread_id": execution_id}}
            final_state = await workflow_instance.workflow.ainvoke(state, config)
        elif hasattr(workflow_instance, 'run'):
            # Custom workflow with run method
            final_state = await workflow_instance.run(state)
        else:
            raise ValueError("Workflow instance must have 'workflow.ainvoke' or 'run' method")
        
        # Extract result
        if isinstance(final_state, dict):
            return final_state
        elif hasattr(final_state, 'dict'):
            return final_state.dict()
        elif hasattr(final_state, '__dict__'):
            return final_state.__dict__
        else:
            return {'result': final_state}
    
    async def cancel_workflow(self, execution_id: str) -> bool:
        """Cancel a running workflow"""
        if execution_id in self.monitor.active_executions:
            self.monitor.complete_execution(
                execution_id,
                WorkflowStatus.CANCELLED,
                error_message="Workflow cancelled by user"
            )
            logger.info(f"Cancelled workflow: {execution_id}")
            return True
        return False
    
    async def get_workflow_status(self, execution_id: str) -> Optional[WorkflowExecution]:
        """Get status of a workflow execution"""
        # Check active executions
        if execution_id in self.monitor.active_executions:
            return self.monitor.active_executions[execution_id]
        
        # Check history
        for execution in self.monitor.execution_history:
            if execution.execution_id == execution_id:
                return execution
        
        return None
    
    async def list_active_workflows(self) -> List[WorkflowExecution]:
        """List all active workflow executions"""
        return list(self.monitor.active_executions.values())
    
    async def get_workflow_metrics(self) -> Dict[str, Any]:
        """Get comprehensive workflow metrics"""
        return {
            'execution_stats': self.monitor.get_execution_stats(),
            'registered_workflows': [wf.value for wf in self.registry.list_workflows()],
            'active_workflows': len(self.monitor.active_executions),
            'total_executions': len(self.monitor.execution_history)
        }
    
    async def cleanup_old_executions(self, max_age_hours: int = 24):
        """Clean up old execution history"""
        cutoff_time = datetime.utcnow() - timedelta(hours=max_age_hours)
        
        initial_count = len(self.monitor.execution_history)
        self.monitor.execution_history = [
            execution for execution in self.monitor.execution_history
            if execution.started_at > cutoff_time
        ]
        
        cleaned_count = initial_count - len(self.monitor.execution_history)
        if cleaned_count > 0:
            logger.info(f"Cleaned up {cleaned_count} old workflow executions")
        
        return cleaned_count
    
    async def health_check(self) -> Dict[str, Any]:
        """Perform health check on workflow manager"""
        health_status = {
            'healthy': True,
            'timestamp': datetime.utcnow().isoformat(),
            'components': {},
            'metrics': {}
        }
        
        try:
            # Check registry
            registered_workflows = self.registry.list_workflows()
            health_status['components']['registry'] = {
                'healthy': len(registered_workflows) > 0,
                'registered_workflows': len(registered_workflows)
            }
            
            # Check monitor
            stats = self.monitor.get_execution_stats()
            health_status['components']['monitor'] = {
                'healthy': True,
                'active_executions': stats.get('active_executions', 0)
            }
            
            # Check recent execution success rate
            recent_executions = [
                e for e in self.monitor.execution_history
                if e.started_at > datetime.utcnow() - timedelta(hours=1)
            ]
            
            if recent_executions:
                success_rate = sum(
                    1 for e in recent_executions
                    if e.status == WorkflowStatus.COMPLETED
                ) / len(recent_executions)
                
                health_status['components']['execution_health'] = {
                    'healthy': success_rate > 0.8,
                    'success_rate': success_rate,
                    'recent_executions': len(recent_executions)
                }
            
            # Overall health
            component_health = [
                comp['healthy'] for comp in health_status['components'].values()
            ]
            health_status['healthy'] = all(component_health)
            
            # Add metrics
            health_status['metrics'] = await self.get_workflow_metrics()
            
        except Exception as e:
            health_status['healthy'] = False
            health_status['error'] = str(e)
            logger.error(f"Workflow manager health check failed: {e}")
        
        return health_status

# Convenience functions
async def execute_simple_search(query: str, user_id: Optional[str] = None) -> Dict[str, Any]:
    """Execute a simple search workflow"""
    manager = WorkflowManager()
    
    input_data = {
        'query': query,
        'user_id': user_id,
        'workflow_complexity': 'simple'
    }
    
    return await manager.execute_workflow(WorkflowType.SIMPLE, input_data)

async def execute_research_workflow(query: str, depth: str = 'deep',
                                  user_id: Optional[str] = None) -> Dict[str, Any]:
    """Execute a research workflow"""
    manager = WorkflowManager()
    
    input_data = {
        'query': query,
        'user_id': user_id,
        'research_depth': depth,
        'workflow_complexity': 'research'
    }
    
    config_overrides = {
        'enable_deep_research': True,
        'max_research_rounds': 3 if depth == 'deep' else 1
    }
    
    return await manager.execute_workflow(
        WorkflowType.RESEARCH, 
        input_data, 
        config_overrides
    )

# Export main classes and functions
__all__ = [
    'WorkflowManager',
    'WorkflowRegistry',
    'WorkflowOptimizer',
    'WorkflowMonitor',
    'WorkflowType',
    'WorkflowStatus',
    'OptimizationLevel',
    'WorkflowExecution',
    'WorkflowConfig',
    'execute_simple_search',
    'execute_research_workflow'
]
