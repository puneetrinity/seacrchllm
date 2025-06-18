# app/ml/model_management.py - AI/ML Model Management & A/B Testing System

import asyncio
import json
import hashlib
import pickle
from typing import Dict, List, Any, Optional, Callable, Union, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from enum import Enum
import uuid
import numpy as np
from pathlib import Path
import logging
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)

class ModelType(str, Enum):
    CLASSIFICATION = "classification"
    REGRESSION = "regression"
    NLP = "nlp"
    EMBEDDING = "embedding"
    RANKING = "ranking"
    RECOMMENDATION = "recommendation"

class ModelStatus(str, Enum):
    TRAINING = "training"
    VALIDATING = "validating"
    TESTING = "testing"
    DEPLOYED = "deployed"
    DEPRECATED = "deprecated"
    FAILED = "failed"

class ExperimentStatus(str, Enum):
    PLANNING = "planning"
    RUNNING = "running"
    ANALYZING = "analyzing"
    COMPLETED = "completed"
    CANCELLED = "cancelled"

@dataclass
class ModelMetadata:
    model_id: str
    name: str
    version: str
    model_type: ModelType
    framework: str  # sklearn, pytorch, tensorflow, etc.
    status: ModelStatus
    created_at: datetime
    updated_at: datetime
    metrics: Dict[str, float]
    hyperparameters: Dict[str, Any]
    training_data_hash: str
    owner: str
    description: str
    tags: List[str]

@dataclass
class ABTestExperiment:
    experiment_id: str
    name: str
    description: str
    status: ExperimentStatus
    start_date: datetime
    end_date: Optional[datetime]
    variants: List[Dict[str, Any]]
    traffic_allocation: Dict[str, float]
    success_metrics: List[str]
    results: Dict[str, Any]
    statistical_significance: Optional[float]
    winner: Optional[str]
    created_by: str

class BaseModel(ABC):
    """Base class for all ML models"""
    
    def __init__(self, model_id: str, metadata: ModelMetadata):
        self.model_id = model_id
        self.metadata = metadata
        self.model = None
        self.is_loaded = False
    
    @abstractmethod
    async def train(self, training_data: Any, validation_data: Any = None) -> Dict[str, Any]:
        """Train the model"""
        pass
    
    @abstractmethod
    async def predict(self, input_data: Any) -> Any:
        """Make predictions"""
        pass
    
    @abstractmethod
    async def evaluate(self, test_data: Any) -> Dict[str, float]:
        """Evaluate model performance"""
        pass
    
    async def load_model(self, model_path: str):
        """Load model from disk"""
        try:
            with open(model_path, 'rb') as f:
                self.model = pickle.load(f)
            self.is_loaded = True
            logger.info(f"Model {self.model_id} loaded successfully")
        except Exception as e:
            logger.error(f"Failed to load model {self.model_id}: {e}")
            raise
    
    async def save_model(self, model_path: str):
        """Save model to disk"""
        try:
            with open(model_path, 'wb') as f:
                pickle.dump(self.model, f)
            logger.info(f"Model {self.model_id} saved to {model_path}")
        except Exception as e:
            logger.error(f"Failed to save model {self.model_id}: {e}")
            raise

class QueryComplexityClassifier(BaseModel):
    """Model for classifying query complexity"""
    
    def __init__(self, model_id: str, metadata: ModelMetadata):
        super().__init__(model_id, metadata)
        
    async def train(self, training_data: Any, validation_data: Any = None) -> Dict[str, Any]:
        """Train query complexity classifier"""
        
        # Feature extraction from queries
        features = []
        labels = []
        
        for query, complexity in training_data:
            feature_vector = self._extract_features(query)
            features.append(feature_vector)
            labels.append(complexity)
        
        features = np.array(features)
        labels = np.array(labels)
        
        # Train simple classifier (in production, use more sophisticated models)
        from sklearn.ensemble import RandomForestClassifier
        from sklearn.model_selection import cross_val_score
        
        self.model = RandomForestClassifier(n_estimators=100, random_state=42)
        self.model.fit(features, labels)
        
        # Cross-validation
        cv_scores = cross_val_score(self.model, features, labels, cv=5)
        
        metrics = {
            "accuracy": cv_scores.mean(),
            "std": cv_scores.std(),
            "feature_importance": dict(zip(
                self._get_feature_names(),
                self.model.feature_importances_
            ))
        }
        
        self.metadata.metrics = metrics
        self.metadata.status = ModelStatus.DEPLOYED
        self.is_loaded = True
        
        return metrics
    
    async def predict(self, input_data: str) -> Dict[str, Any]:
        """Predict query complexity"""
        
        if not self.is_loaded:
            raise ValueError("Model not loaded")
        
        features = self._extract_features(input_data)
        complexity_class = self.model.predict([features])[0]
        probability = self.model.predict_proba([features])[0].max()
        
        return {
            "complexity_class": complexity_class,
            "confidence": probability,
            "features_used": self._get_feature_names()
        }
    
    async def evaluate(self, test_data: Any) -> Dict[str, float]:
        """Evaluate classifier performance"""
        
        features = []
        true_labels = []
        
        for query, complexity in test_data:
            feature_vector = self._extract_features(query)
            features.append(feature_vector)
            true_labels.append(complexity)
        
        features = np.array(features)
        predicted_labels = self.model.predict(features)
        
        from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score
        
        return {
            "accuracy": accuracy_score(true_labels, predicted_labels),
            "precision": precision_score(true_labels, predicted_labels, average='weighted'),
            "recall": recall_score(true_labels, predicted_labels, average='weighted'),
            "f1_score": f1_score(true_labels, predicted_labels, average='weighted')
        }
    
    def _extract_features(self, query: str) -> List[float]:
        """Extract features from query"""
        
        features = []
        
        # Basic text features
        features.append(len(query))  # Query length
        features.append(len(query.split()))  # Word count
        features.append(query.count('?'))  # Question marks
        features.append(query.count(','))  # Commas
        features.append(query.count('and'))  # Conjunctions
        features.append(query.count('or'))  # Disjunctions
        
        # Complexity indicators
        long_words = [word for word in query.split() if len(word) > 8]
        features.append(len(long_words))  # Long words count
        
        # Question type features
        question_words = ['what', 'how', 'why', 'when', 'where', 'who']
        features.append(sum(1 for word in question_words if word in query.lower()))
        
        # Technical terms (simplified)
        technical_words = ['algorithm', 'analysis', 'implementation', 'optimization']
        features.append(sum(1 for word in technical_words if word in query.lower()))
        
        return features
    
    def _get_feature_names(self) -> List[str]:
        """Get feature names for interpretability"""
        return [
            "query_length", "word_count", "question_marks", "commas",
            "conjunctions", "disjunctions", "long_words", "question_words",
            "technical_terms"
        ]

class SearchRelevanceRanker(BaseModel):
    """Model for ranking search result relevance"""
    
    def __init__(self, model_id: str, metadata: ModelMetadata):
        super().__init__(model_id, metadata)
    
    async def train(self, training_data: Any, validation_data: Any = None) -> Dict[str, Any]:
        """Train relevance ranking model"""
        
        # Training data format: [(query, result, relevance_score), ...]
        features = []
        scores = []
        
        for query, result, relevance in training_data:
            feature_vector = self._extract_ranking_features(query, result)
            features.append(feature_vector)
            scores.append(relevance)
        
        features = np.array(features)
        scores = np.array(scores)
        
        # Train regression model
        from sklearn.ensemble import GradientBoostingRegressor
        from sklearn.model_selection import train_test_split
        from sklearn.metrics import mean_squared_error, r2_score
        
        X_train, X_test, y_train, y_test = train_test_split(
            features, scores, test_size=0.2, random_state=42
        )
        
        self.model = GradientBoostingRegressor(n_estimators=100, random_state=42)
        self.model.fit(X_train, y_train)
        
        # Evaluate
        y_pred = self.model.predict(X_test)
        
        metrics = {
            "mse": mean_squared_error(y_test, y_pred),
            "r2_score": r2_score(y_test, y_pred),
            "feature_importance": dict(zip(
                self._get_ranking_feature_names(),
                self.model.feature_importances_
            ))
        }
        
        self.metadata.metrics = metrics
        self.metadata.status = ModelStatus.DEPLOYED
        self.is_loaded = True
        
        return metrics
    
    async def predict(self, input_data: Tuple[str, Dict[str, Any]]) -> float:
        """Predict relevance score"""
        
        query, result = input_data
        features = self._extract_ranking_features(query, result)
        relevance_score = self.model.predict([features])[0]
        
        return max(0.0, min(1.0, relevance_score))  # Clamp to [0, 1]
    
    def _extract_ranking_features(self, query: str, result: Dict[str, Any]) -> List[float]:
        """Extract features for ranking"""
        
        features = []
        
        title = result.get('title', '')
        snippet = result.get('snippet', '')
        url = result.get('url', '')
        
        # Query-title similarity
        query_words = set(query.lower().split())
        title_words = set(title.lower().split())
        title_overlap = len(query_words.intersection(title_words)) / max(1, len(query_words))
        features.append(title_overlap)
        
        # Query-snippet similarity
        snippet_words = set(snippet.lower().split())
        snippet_overlap = len(query_words.intersection(snippet_words)) / max(1, len(query_words))
        features.append(snippet_overlap)
        
        # Domain authority (simplified)
        domain_score = 0.5  # Default
        if any(domain in url for domain in ['wikipedia.org', 'stackoverflow.com', 'github.com']):
            domain_score = 0.9
        elif any(domain in url for domain in ['.edu', '.gov']):
            domain_score = 0.8
        features.append(domain_score)
        
        # Content length indicators
        features.append(len(title))
        features.append(len(snippet))
        
        # Position features (if available)
        features.append(result.get('position', 10) / 10.0)  # Normalize position
        
        return features
    
    def _get_ranking_feature_names(self) -> List[str]:
        return [
            "title_overlap", "snippet_overlap", "domain_authority",
            "title_length", "snippet_length", "search_position"
        ]

class MLModelManager:
    """Comprehensive ML model management system"""
    
    def __init__(self):
        self.models: Dict[str, BaseModel] = {}
        self.experiments: Dict[str, ABTestExperiment] = {}
        self.model_registry: Dict[str, ModelMetadata] = {}
        self.deployment_configs: Dict[str, Dict[str, Any]] = {}
        
        # Model performance tracking
        self.performance_history: Dict[str, List[Dict[str, Any]]] = {}
        self.model_usage_stats: Dict[str, Dict[str, Any]] = {}
        
        # A/B testing infrastructure
        self.experiment_traffic_router = ExperimentTrafficRouter()
        
    async def register_model(self, 
                           model: BaseModel,
                           deployment_config: Dict[str, Any] = None) -> str:
        """Register a new model"""
        
        model_id = model.model_id
        
        # Store model and metadata
        self.models[model_id] = model
        self.model_registry[model_id] = model.metadata
        
        if deployment_config:
            self.deployment_configs[model_id] = deployment_config
        
        # Initialize performance tracking
        self.performance_history[model_id] = []
        self.model_usage_stats[model_id] = {
            "total_predictions": 0,
            "total_training_runs": 0,
            "average_prediction_time": 0.0,
            "last_used": None,
            "error_count": 0
        }
        
        logger.info(f"Model {model_id} registered successfully")
        return model_id
    
    async def deploy_model(self, 
                         model_id: str,
                         environment: str = "production",
                         traffic_percentage: float = 100.0) -> Dict[str, Any]:
        """Deploy model to specified environment"""
        
        if model_id not in self.models:
            raise ValueError(f"Model {model_id} not found")
        
        model = self.models[model_id]
        
        # Validate model is ready for deployment
        if model.metadata.status != ModelStatus.DEPLOYED:
            raise ValueError(f"Model {model_id} is not ready for deployment (status: {model.metadata.status})")
        
        # Create deployment configuration
        deployment = {
            "model_id": model_id,
            "environment": environment,
            "traffic_percentage": traffic_percentage,
            "deployed_at": datetime.now(),
            "version": model.metadata.version,
            "health_check_endpoint": f"/models/{model_id}/health",
            "prediction_endpoint": f"/models/{model_id}/predict"
        }
        
        # Update deployment configs
        if model_id not in self.deployment_configs:
            self.deployment_configs[model_id] = {}
        
        self.deployment_configs[model_id][environment] = deployment
        
        logger.info(f"Model {model_id} deployed to {environment} with {traffic_percentage}% traffic")
        
        return deployment
    
    async def create_ab_experiment(self,
                                 name: str,
                                 description: str,
                                 variants: List[Dict[str, Any]],
                                 traffic_allocation: Dict[str, float],
                                 success_metrics: List[str],
                                 duration_days: int = 14) -> str:
        """Create A/B test experiment"""
        
        experiment_id = str(uuid.uuid4())
        
        # Validate traffic allocation
        if abs(sum(traffic_allocation.values()) - 1.0) > 0.01:
            raise ValueError("Traffic allocation must sum to 1.0")
        
        experiment = ABTestExperiment(
            experiment_id=experiment_id,
            name=name,
            description=description,
            status=ExperimentStatus.PLANNING,
            start_date=datetime.now(),
            end_date=datetime.now() + timedelta(days=duration_days),
            variants=variants,
            traffic_allocation=traffic_allocation,
            success_metrics=success_metrics,
            results={},
            statistical_significance=None,
            winner=None,
            created_by="system"  # In production, get from auth context
        )
        
        self.experiments[experiment_id] = experiment
        
        # Configure traffic router
        await self.experiment_traffic_router.setup_experiment(experiment)
        
        logger.info(f"A/B experiment {experiment_id} created: {name}")
        
        return experiment_id
    
    async def start_experiment(self, experiment_id: str) -> Dict[str, Any]:
        """Start A/B test experiment"""
        
        if experiment_id not in self.experiments:
            raise ValueError(f"Experiment {experiment_id} not found")
        
        experiment = self.experiments[experiment_id]
        experiment.status = ExperimentStatus.RUNNING
        experiment.start_date = datetime.now()
        
        # Activate traffic routing
        await self.experiment_traffic_router.activate_experiment(experiment_id)
        
        logger.info(f"A/B experiment {experiment_id} started")
        
        return {
            "experiment_id": experiment_id,
            "status": "running",
            "start_date": experiment.start_date.isoformat(),
            "variants": [v["name"] for v in experiment.variants],
            "traffic_allocation": experiment.traffic_allocation
        }
    
    async def get_model_prediction(self,
                                 model_id: str,
                                 input_data: Any,
                                 experiment_context: Dict[str, Any] = None) -> Dict[str, Any]:
        """Get prediction from model (with A/B testing support)"""
        
        start_time = datetime.now()
        
        try:
            # Check if this request is part of an active experiment
            if experiment_context:
                model_variant = await self.experiment_traffic_router.route_request(
                    experiment_context, model_id
                )
                if model_variant != model_id:
                    # Use experiment variant
                    actual_model_id = model_variant
                else:
                    actual_model_id = model_id
            else:
                actual_model_id = model_id
            
            # Get prediction
            model = self.models[actual_model_id]
            prediction = await model.predict(input_data)
            
            processing_time = (datetime.now() - start_time).total_seconds()
            
            # Update usage statistics
            await self._update_model_usage_stats(actual_model_id, processing_time, success=True)
            
            # Track experiment metrics if applicable
            if experiment_context:
                await self._track_experiment_metrics(
                    experiment_context.get("experiment_id"),
                    actual_model_id,
                    prediction,
                    processing_time
                )
            
            return {
                "model_id": actual_model_id,
                "prediction": prediction,
                "processing_time": processing_time,
                "experiment_variant": actual_model_id if experiment_context else None,
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            # Update error statistics
            await self._update_model_usage_stats(model_id, 0, success=False)
            
            logger.error(f"Prediction failed for model {model_id}: {e}")
            raise
    
    async def analyze_experiment_results(self, experiment_id: str) -> Dict[str, Any]:
        """Analyze A/B experiment results"""
        
        if experiment_id not in self.experiments:
            raise ValueError(f"Experiment {experiment_id} not found")
        
        experiment = self.experiments[experiment_id]
        
        # Get experiment data
        experiment_data = await self.experiment_traffic_router.get_experiment_data(experiment_id)
        
        # Statistical analysis
        analysis = await self._perform_statistical_analysis(experiment_data, experiment.success_metrics)
        
        # Update experiment with results
        experiment.results = analysis["results"]
        experiment.statistical_significance = analysis["significance"]
        experiment.winner = analysis["winner"]
        
        if analysis["significant"]:
            experiment.status = ExperimentStatus.COMPLETED
        
        return {
            "experiment_id": experiment_id,
            "status": experiment.status.value,
            "results": analysis,
            "recommendation": await self._generate_experiment_recommendation(analysis),
            "next_steps": await self._suggest_next_steps(experiment, analysis)
        }
    
    async def _perform_statistical_analysis(self, 
                                          experiment_data: Dict[str, Any],
                                          success_metrics: List[str]) -> Dict[str, Any]:
        """Perform statistical analysis of experiment results"""
        
        results = {}
        significance_tests = {}
        
        for metric in success_metrics:
            metric_data = experiment_data.get(metric, {})
            
            if len(metric_data) >= 2:  # Need at least 2 variants
                # Perform statistical test (simplified t-test)
                from scipy import stats
                
                variant_names = list(metric_data.keys())
                variant_a_data = metric_data[variant_names[0]]
                variant_b_data = metric_data[variant_names[1]]
                
                if len(variant_a_data) > 0 and len(variant_b_data) > 0:
                    t_stat, p_value = stats.ttest_ind(variant_a_data, variant_b_data)
                    
                    results[metric] = {
                        "variant_a": {
                            "name": variant_names[0],
                            "mean": np.mean(variant_a_data),
                            "std": np.std(variant_a_data),
                            "count": len(variant_a_data)
                        },
                        "variant_b": {
                            "name": variant_names[1],
                            "mean": np.mean(variant_b_data),
                            "std": np.std(variant_b_data),
                            "count": len(variant_b_data)
                        },
                        "statistical_test": {
                            "t_statistic": t_stat,
                            "p_value": p_value,
                            "significant": p_value < 0.05
                        }
                    }
                    
                    significance_tests[metric] = p_value < 0.05
        
        # Determine overall significance and winner
        overall_significant = any(significance_tests.values())
        
        if overall_significant:
            # Find best performing variant across metrics
            winner = await self._determine_winner(results, success_metrics)
        else:
            winner = None
        
        return {
            "results": results,
            "significance": min(significance_tests.values()) if significance_tests else 1.0,
            "significant": overall_significant,
            "winner": winner
        }

class ExperimentTrafficRouter:
    """Traffic routing for A/B experiments"""
    
    def __init__(self):
        self.active_experiments: Dict[str, ABTestExperiment] = {}
        self.experiment_data: Dict[str, Dict[str, List[float]]] = {}
        
    async def setup_experiment(self, experiment: ABTestExperiment):
        """Setup experiment for traffic routing"""
        
        self.experiment_data[experiment.experiment_id] = {
            metric: {variant["name"]: [] for variant in experiment.variants}
            for metric in experiment.success_metrics
        }
    
    async def activate_experiment(self, experiment_id: str):
        """Activate experiment for traffic routing"""
        
        # In production, this would configure load balancers, feature flags, etc.
        logger.info(f"Experiment {experiment_id} activated for traffic routing")
    
    async def route_request(self, 
                          context: Dict[str, Any], 
                          default_model_id: str) -> str:
        """Route request to appropriate model variant"""
        
        experiment_id = context.get("experiment_id")
        user_id = context.get("user_id", "anonymous")
        
        if experiment_id not in self.active_experiments:
            return default_model_id
        
        experiment = self.active_experiments[experiment_id]
        
        # Consistent routing based on user ID hash
        user_hash = hashlib.md5(user_id.encode()).hexdigest()
        hash_value = int(user_hash[:8], 16) / 0xFFFFFFFF
        
        # Route based on traffic allocation
        cumulative_probability = 0.0
        for variant_name, probability in experiment.traffic_allocation.items():
            cumulative_probability += probability
            if hash_value <= cumulative_probability:
                # Find variant model ID
                for variant in experiment.variants:
                    if variant["name"] == variant_name:
                        return variant.get("model_id", default_model_id)
        
        return default_model_id
    
    async def track_experiment_metric(self,
                                    experiment_id: str,
                                    variant_name: str,
                                    metric_name: str,
                                    value: float):
        """Track experiment metric value"""
        
        if experiment_id in self.experiment_data:
            if metric_name in self.experiment_data[experiment_id]:
                if variant_name in self.experiment_data[experiment_id][metric_name]:
                    self.experiment_data[experiment_id][metric_name][variant_name].append(value)
    
    async def get_experiment_data(self, experiment_id: str) -> Dict[str, Any]:
        """Get experiment data for analysis"""
        
        return self.experiment_data.get(experiment_id, {})

# Final Integration System
class ProductionIntegrationOrchestrator:
    """Complete production system orchestrator"""
    
    def __init__(self):
        # Initialize all subsystems
        from app.analytics.realtime_system import RealTimeAnalyticsEngine
        from app.security.compliance_framework import SecurityComplianceEngine
        from app.optimization.cost_management import SmartCostOptimizer, MultiTenantArchitecture
        from app.vector.semantic_search import VectorEnhancedSearchWorkflow
        from app.langgraph.advanced.premium_patterns import PremiumSearchOrchestrator
        
        # Core systems
        self.analytics = RealTimeAnalyticsEngine()
        self.security = SecurityComplianceEngine()
        self.cost_optimizer = SmartCostOptimizer()
        self.multi_tenant = MultiTenantArchitecture(self.cost_optimizer)
        self.ml_manager = MLModelManager()
        
        # Search systems
        self.premium_search = PremiumSearchOrchestrator()
        self.vector_search = VectorEnhancedSearchWorkflow(
            vector_config={"provider": "chromadb"},
            embedding_config={"provider": "sentence_transformers", "model_name": "all-MiniLM-L6-v2"}
        )
        
        # Integration state
        self.health_status = {}
        self.system_metrics = {}
        
    async def execute_production_search(self,
                                      query: str,
                                      tenant_id: str,
                                      user_id: Optional[str] = None,
                                      experiment_context: Dict[str, Any] = None,
                                      compliance_frameworks: List[str] = None) -> Dict[str, Any]:
        """Execute complete production search with all systems integrated"""
        
        request_id = str(uuid.uuid4())
        start_time = datetime.now()
        
        try:
            # 1. Security and compliance validation
            security_validation = await self.security.validate_compliance(
                action="search_execution",
                data={"query": query, "tenant_id": tenant_id},
                user_context={"user_id": user_id, "tenant_id": tenant_id},
                frameworks=[ComplianceFramework(f) for f in (compliance_frameworks or ["gdpr"])]
            )
            
            if not security_validation["compliant"]:
                return {
                    "error": "Compliance violation",
                    "violations": security_validation["violations"],
                    "request_id": request_id
                }
            
            # 2. PII detection and protection
            pii_result = await self.security.detect_and_protect_pii(query)
            protected_query = pii_result["protected_content"]
            
            # 3. Get optimal search strategy using ML
            complexity_prediction = await self.ml_manager.get_model_prediction(
                model_id="query_complexity_classifier",
                input_data=protected_query,
                experiment_context=experiment_context
            )
            
            # 4. Cost estimation and optimization
            search_strategy = await self.multi_tenant.get_tenant_search_strategy(
                tenant_id, protected_query
            )
            
            cost_estimate = await self.cost_optimizer.estimate_query_cost(
                protected_query, search_strategy, tenant_id
            )
            
            # 5. Execute premium LangGraph search
            if complexity_prediction["prediction"]["complexity_class"] == "complex":
                workflow_pattern = WorkflowPattern.COLLABORATIVE
            elif "urgent" in query.lower():
                workflow_pattern = WorkflowPattern.REAL_TIME_ADAPTIVE
            else:
                workflow_pattern = WorkflowPattern.SELF_CORRECTING
            
            search_result = await self.premium_search.execute_premium_search(
                query=protected_query,
                pattern=workflow_pattern,
                user_context={"user_id": user_id, "tenant_id": tenant_id}
            )
            
            # 6. Vector enhancement
            vector_enhancement = await self.vector_search.vector_enhanced_search(
                query=protected_query,
                traditional_results=search_result.get("search_results", [])
            )
            
            # 7. Result ranking using ML
            if "search_result_ranker" in self.ml_manager.models:
                ranked_results = []
                for result in vector_enhancement["result"]["sources"]:
                    ranking_score = await self.ml_manager.get_model_prediction(
                        model_id="search_result_ranker",
                        input_data=(protected_query, result)
                    )
                    result["ml_ranking_score"] = ranking_score["prediction"]
                    ranked_results.append(result)
                
                # Sort by ML ranking
                ranked_results.sort(key=lambda x: x.get("ml_ranking_score", 0), reverse=True)
                vector_enhancement["result"]["sources"] = ranked_results
            
            processing_time = (datetime.now() - start_time).total_seconds()
            
            # 8. Track metrics and costs
            await self.analytics.record_metric("search_latency", processing_time, tenant_id=tenant_id)
            await self.analytics.record_metric("query_complexity_distribution", 
                                             complexity_prediction["prediction"]["confidence"], 
                                             tenant_id=tenant_id)
            
            actual_cost = cost_estimate["total_estimated_cost"]  # Simplified
            await self.cost_optimizer.track_cost(
                category=CostCategory.SEARCH_ENGINES,
                subcategory="production_search",
                amount=actual_cost,
                tenant_id=tenant_id,
                user_id=user_id,
                request_id=request_id
            )
            
            # 9. Audit logging
            await self.security.audit_log(
                action="production_search",
                resource=f"query:{protected_query[:50]}",
                result="success",
                user_id=user_id,
                tenant_id=tenant_id,
                details={
                    "request_id": request_id,
                    "processing_time": processing_time,
                    "cost": actual_cost,
                    "pii_detected": len(pii_result["pii_detected"]) > 0,
                    "complexity_class": complexity_prediction["prediction"]["complexity_class"]
                }
            )
            
            # 10. Final response assembly
            final_response = {
                "request_id": request_id,
                "query": query,  # Original query for response
                "answer": vector_enhancement["result"]["answer"],
                "sources": vector_enhancement["result"]["sources"],
                "metadata": {
                    "processing_time": processing_time,
                    "cost": actual_cost,
                    "tenant_id": tenant_id,
                    "workflow_pattern": workflow_pattern.value,
                    "complexity_prediction": complexity_prediction["prediction"],
                    "pii_protection": {
                        "applied": len(pii_result["pii_detected"]) > 0,
                        "types_detected": pii_result["pii_detected"]
                    },
                    "compliance_status": security_validation["compliant"],
                    "vector_enhancement": vector_enhancement["enhancement_applied"],
                    "ml_ranking_applied": "search_result_ranker" in self.ml_manager.models
                },
                "quality_score": search_result.get("confidence_score", 0.8),
                "timestamp": datetime.now().isoformat()
            }
            
            return final_response
            
        except Exception as e:
            # Error handling and logging
            processing_time = (datetime.now() - start_time).total_seconds()
            
            await self.analytics.record_metric("error_rate", 1.0, tenant_id=tenant_id)
            await self.security.audit_log(
                action="production_search",
                resource=f"query:{query[:50]}",
                result="error",
                user_id=user_id,
                tenant_id=tenant_id,
                details={"request_id": request_id, "error": str(e), "processing_time": processing_time}
            )
            
            logger.error(f"Production search failed for request {request_id}: {e}")
            
            return {
                "error": "Search execution failed",
                "request_id": request_id,
                "processing_time": processing_time,
                "timestamp": datetime.now().isoformat()
            }
    
    async def get_system_health(self) -> Dict[str, Any]:
        """Get comprehensive system health status"""
        
        health_checks = {
            "analytics": await self._check_analytics_health(),
            "security": await self._check_security_health(),
            "cost_optimizer": await self._check_cost_optimizer_health(),
            "ml_models": await self._check_ml_models_health(),
            "vector_search": await self._check_vector_search_health(),
            "premium_search": await self._check_premium_search_health()
        }
        
        overall_healthy = all(check["status"] == "healthy" for check in health_checks.values())
        
        return {
            "overall_status": "healthy" if overall_healthy else "degraded",
            "components": health_checks,
            "timestamp": datetime.now().isoformat(),
            "system_version": "2.0.0-production"
        }
    
    async def _check_analytics_health(self) -> Dict[str, Any]:
        """Check analytics system health"""
        try:
            # Test metric recording
            await self.analytics.record_metric("health_check", 1.0)
            return {"status": "healthy", "last_check": datetime.now().isoformat()}
        except Exception as e:
            return {"status": "unhealthy", "error": str(e)}
    
    async def _check_ml_models_health(self) -> Dict[str, Any]:
        """Check ML models health"""
        try:
            model_statuses = {}
            for model_id, model in self.ml_manager.models.items():
                if model.is_loaded:
                    model_statuses[model_id] = "loaded"
                else:
                    model_statuses[model_id] = "not_loaded"
            
            return {
                "status": "healthy" if model_statuses else "no_models",
                "models": model_statuses,
                "total_models": len(self.ml_manager.models)
            }
        except Exception as e:
            return {"status": "unhealthy", "error": str(e)}
