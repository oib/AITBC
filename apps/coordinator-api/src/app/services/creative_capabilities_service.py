"""
Creative Capabilities Service
Implements advanced creativity enhancement systems and specialized AI capabilities
"""

import asyncio
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from uuid import uuid4
import logging
import random

from sqlmodel import Session, select, update, delete, and_, or_, func
from sqlalchemy.exc import SQLAlchemyError

from ..domain.agent_performance import (
    CreativeCapability, AgentCapability, AgentPerformanceProfile
)

logger = logging.getLogger(__name__)


class CreativityEnhancementEngine:
    """Advanced creativity enhancement system for OpenClaw agents"""
    
    def __init__(self):
        self.enhancement_algorithms = {
            'divergent_thinking': self.divergent_thinking_enhancement,
            'conceptual_blending': self.conceptual_blending,
            'morphological_analysis': self.morphological_analysis,
            'lateral_thinking': self.lateral_thinking_stimulation,
            'bisociation': self.bisociation_framework
        }
        
        self.creative_domains = {
            'artistic': ['visual_arts', 'music_composition', 'literary_arts'],
            'design': ['ui_ux', 'product_design', 'architectural'],
            'innovation': ['problem_solving', 'product_innovation', 'process_innovation'],
            'scientific': ['hypothesis_generation', 'experimental_design'],
            'narrative': ['storytelling', 'world_building', 'character_development']
        }
        
        self.evaluation_metrics = [
            'originality',
            'fluency',
            'flexibility',
            'elaboration',
            'aesthetic_value',
            'utility'
        ]
    
    async def create_creative_capability(
        self, 
        session: Session,
        agent_id: str,
        creative_domain: str,
        capability_type: str,
        generation_models: List[str],
        initial_score: float = 0.5
    ) -> CreativeCapability:
        """Initialize a new creative capability for an agent"""
        
        capability_id = f"creative_{uuid4().hex[:8]}"
        
        # Determine specialized areas based on domain
        specializations = self.creative_domains.get(creative_domain, ['general_creativity'])
        
        capability = CreativeCapability(
            capability_id=capability_id,
            agent_id=agent_id,
            creative_domain=creative_domain,
            capability_type=capability_type,
            originality_score=initial_score,
            novelty_score=initial_score * 0.9,
            aesthetic_quality=initial_score * 5.0,
            coherence_score=initial_score * 1.1,
            generation_models=generation_models,
            creative_learning_rate=0.05,
            creative_specializations=specializations,
            status="developing",
            created_at=datetime.utcnow()
        )
        
        session.add(capability)
        session.commit()
        session.refresh(capability)
        
        logger.info(f"Created creative capability {capability_id} for agent {agent_id}")
        return capability
    
    async def enhance_creativity(
        self, 
        session: Session,
        capability_id: str,
        algorithm: str = "divergent_thinking",
        training_cycles: int = 100
    ) -> Dict[str, Any]:
        """Enhance a specific creative capability"""
        
        capability = session.exec(
            select(CreativeCapability).where(CreativeCapability.capability_id == capability_id)
        ).first()
        
        if not capability:
            raise ValueError(f"Creative capability {capability_id} not found")
        
        try:
            # Apply enhancement algorithm
            enhancement_func = self.enhancement_algorithms.get(
                algorithm, 
                self.divergent_thinking_enhancement
            )
            
            enhancement_results = await enhancement_func(capability, training_cycles)
            
            # Update capability metrics
            capability.originality_score = min(1.0, capability.originality_score + enhancement_results['originality_gain'])
            capability.novelty_score = min(1.0, capability.novelty_score + enhancement_results['novelty_gain'])
            capability.aesthetic_quality = min(5.0, capability.aesthetic_quality + enhancement_results['aesthetic_gain'])
            capability.style_variety += enhancement_results['variety_gain']
            
            # Track training history
            capability.creative_metadata['last_enhancement'] = {
                'algorithm': algorithm,
                'cycles': training_cycles,
                'results': enhancement_results,
                'timestamp': datetime.utcnow().isoformat()
            }
            
            # Update status if ready
            if capability.originality_score > 0.8 and capability.aesthetic_quality > 4.0:
                capability.status = "certified"
            elif capability.originality_score > 0.6:
                capability.status = "ready"
                
            capability.updated_at = datetime.utcnow()
            
            session.commit()
            
            logger.info(f"Enhanced creative capability {capability_id} using {algorithm}")
            return {
                'success': True,
                'capability_id': capability_id,
                'algorithm': algorithm,
                'improvements': enhancement_results,
                'new_scores': {
                    'originality': capability.originality_score,
                    'novelty': capability.novelty_score,
                    'aesthetic': capability.aesthetic_quality,
                    'variety': capability.style_variety
                },
                'status': capability.status
            }
            
        except Exception as e:
            logger.error(f"Error enhancing creativity for {capability_id}: {str(e)}")
            raise
    
    async def divergent_thinking_enhancement(self, capability: CreativeCapability, cycles: int) -> Dict[str, float]:
        """Enhance divergent thinking capabilities"""
        
        # Simulate divergent thinking training
        base_learning_rate = capability.creative_learning_rate
        
        originality_gain = base_learning_rate * (cycles / 100) * random.uniform(0.8, 1.2)
        variety_gain = int(max(1, cycles / 50) * random.uniform(0.5, 1.5))
        
        return {
            'originality_gain': originality_gain,
            'novelty_gain': originality_gain * 0.8,
            'aesthetic_gain': originality_gain * 2.0,  # Scale to 0-5
            'variety_gain': variety_gain,
            'fluency_improvement': random.uniform(0.1, 0.3)
        }
    
    async def conceptual_blending(self, capability: CreativeCapability, cycles: int) -> Dict[str, float]:
        """Enhance conceptual blending (combining unrelated concepts)"""
        
        base_learning_rate = capability.creative_learning_rate
        
        novelty_gain = base_learning_rate * (cycles / 80) * random.uniform(0.9, 1.3)
        
        return {
            'originality_gain': novelty_gain * 0.7,
            'novelty_gain': novelty_gain,
            'aesthetic_gain': novelty_gain * 1.5,
            'variety_gain': int(cycles / 60),
            'blending_efficiency': random.uniform(0.15, 0.35)
        }
    
    async def morphological_analysis(self, capability: CreativeCapability, cycles: int) -> Dict[str, float]:
        """Enhance morphological analysis (systematic exploration of possibilities)"""
        
        base_learning_rate = capability.creative_learning_rate
        
        # Morphological analysis is systematic, so steady gains
        gain = base_learning_rate * (cycles / 100)
        
        return {
            'originality_gain': gain * 0.9,
            'novelty_gain': gain * 1.1,
            'aesthetic_gain': gain * 1.0,
            'variety_gain': int(cycles / 40),
            'systematic_coverage': random.uniform(0.2, 0.4)
        }
    
    async def lateral_thinking_stimulation(self, capability: CreativeCapability, cycles: int) -> Dict[str, float]:
        """Enhance lateral thinking (approaching problems from new angles)"""
        
        base_learning_rate = capability.creative_learning_rate
        
        # Lateral thinking produces highly original but sometimes less coherent results
        gain = base_learning_rate * (cycles / 90) * random.uniform(0.7, 1.5)
        
        return {
            'originality_gain': gain * 1.3,
            'novelty_gain': gain * 1.2,
            'aesthetic_gain': gain * 0.8,
            'variety_gain': int(cycles / 50),
            'perspective_shifts': random.uniform(0.2, 0.5)
        }
    
    async def bisociation_framework(self, capability: CreativeCapability, cycles: int) -> Dict[str, float]:
        """Enhance bisociation (connecting two previously unrelated frames of reference)"""
        
        base_learning_rate = capability.creative_learning_rate
        
        gain = base_learning_rate * (cycles / 120) * random.uniform(0.8, 1.4)
        
        return {
            'originality_gain': gain * 1.4,
            'novelty_gain': gain * 1.3,
            'aesthetic_gain': gain * 1.2,
            'variety_gain': int(cycles / 70),
            'cross_domain_links': random.uniform(0.1, 0.4)
        }
    
    async def evaluate_creation(
        self, 
        session: Session,
        capability_id: str,
        creation_data: Dict[str, Any],
        expert_feedback: Optional[Dict[str, float]] = None
    ) -> Dict[str, Any]:
        """Evaluate a creative output and update capability"""
        
        capability = session.exec(
            select(CreativeCapability).where(CreativeCapability.capability_id == capability_id)
        ).first()
        
        if not capability:
            raise ValueError(f"Creative capability {capability_id} not found")
        
        # Perform automated evaluation
        auto_eval = self.automated_aesthetic_evaluation(creation_data, capability.creative_domain)
        
        # Combine with expert feedback if available
        final_eval = {}
        for metric in self.evaluation_metrics:
            auto_score = auto_eval.get(metric, 0.5)
            if expert_feedback and metric in expert_feedback:
                # Expert feedback is weighted more heavily
                final_eval[metric] = (auto_score * 0.3) + (expert_feedback[metric] * 0.7)
            else:
                final_eval[metric] = auto_score
        
        # Update capability based on evaluation
        capability.creations_generated += 1
        
        # Moving average update of quality metrics
        alpha = 0.1  # Learning rate for metrics
        capability.originality_score = (1 - alpha) * capability.originality_score + alpha * final_eval.get('originality', capability.originality_score)
        capability.aesthetic_quality = (1 - alpha) * capability.aesthetic_quality + alpha * (final_eval.get('aesthetic_value', 0.5) * 5.0)
        capability.coherence_score = (1 - alpha) * capability.coherence_score + alpha * final_eval.get('utility', capability.coherence_score)
        
        # Record evaluation
        evaluation_record = {
            'timestamp': datetime.utcnow().isoformat(),
            'creation_id': creation_data.get('id', f"create_{uuid4().hex[:8]}"),
            'scores': final_eval
        }
        
        evaluations = capability.expert_evaluations
        evaluations.append(evaluation_record)
        # Keep only last 50 evaluations
        if len(evaluations) > 50:
            evaluations = evaluations[-50:]
        capability.expert_evaluations = evaluations
        
        capability.last_evaluation = datetime.utcnow()
        session.commit()
        
        return {
            'success': True,
            'evaluation': final_eval,
            'capability_updated': True,
            'new_aesthetic_quality': capability.aesthetic_quality
        }
    
    def automated_aesthetic_evaluation(self, creation_data: Dict[str, Any], domain: str) -> Dict[str, float]:
        """Automated evaluation of creative outputs based on domain heuristics"""
        
        # Simulated automated evaluation logic
        # In a real system, this would use specialized models to evaluate art, text, music, etc.
        
        content = str(creation_data.get('content', ''))
        complexity = min(1.0, len(content) / 1000.0)
        structure_score = 0.5 + (random.uniform(-0.2, 0.3))
        
        if domain == 'artistic':
            return {
                'originality': random.uniform(0.6, 0.95),
                'fluency': complexity,
                'flexibility': random.uniform(0.5, 0.8),
                'elaboration': structure_score,
                'aesthetic_value': random.uniform(0.7, 0.9),
                'utility': random.uniform(0.4, 0.7)
            }
        elif domain == 'innovation':
            return {
                'originality': random.uniform(0.7, 0.9),
                'fluency': structure_score,
                'flexibility': random.uniform(0.6, 0.9),
                'elaboration': complexity,
                'aesthetic_value': random.uniform(0.5, 0.8),
                'utility': random.uniform(0.8, 0.95)
            }
        else:
            return {
                'originality': random.uniform(0.5, 0.9),
                'fluency': random.uniform(0.5, 0.9),
                'flexibility': random.uniform(0.5, 0.9),
                'elaboration': random.uniform(0.5, 0.9),
                'aesthetic_value': random.uniform(0.5, 0.9),
                'utility': random.uniform(0.5, 0.9)
            }


class IdeationAlgorithm:
    """System for generating innovative ideas and solving complex problems"""
    
    def __init__(self):
        self.ideation_techniques = {
            'scamper': self.scamper_technique,
            'triz': self.triz_inventive_principles,
            'six_thinking_hats': self.six_thinking_hats,
            'first_principles': self.first_principles_reasoning,
            'biomimicry': self.biomimicry_mapping
        }
    
    async def generate_ideas(
        self,
        problem_statement: str,
        domain: str,
        technique: str = "scamper",
        num_ideas: int = 5,
        constraints: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Generate innovative ideas using specified technique"""
        
        technique_func = self.ideation_techniques.get(technique, self.first_principles_reasoning)
        
        # Simulate idea generation process
        await asyncio.sleep(0.5)  # Processing time
        
        ideas = []
        for i in range(num_ideas):
            idea = technique_func(problem_statement, domain, i, constraints)
            ideas.append(idea)
            
        # Rank ideas by novelty and feasibility
        ranked_ideas = self.rank_ideas(ideas)
        
        return {
            'problem': problem_statement,
            'technique_used': technique,
            'domain': domain,
            'generated_ideas': ranked_ideas,
            'generation_timestamp': datetime.utcnow().isoformat()
        }
    
    def scamper_technique(self, problem: str, domain: str, seed: int, constraints: Any) -> Dict[str, Any]:
        """Substitute, Combine, Adapt, Modify, Put to another use, Eliminate, Reverse"""
        operations = ['Substitute', 'Combine', 'Adapt', 'Modify', 'Put to other use', 'Eliminate', 'Reverse']
        op = operations[seed % len(operations)]
        
        return {
            'title': f"{op}-based innovation for {domain}",
            'description': f"Applying the {op} principle to solving: {problem[:30]}...",
            'technique_aspect': op,
            'novelty_score': random.uniform(0.6, 0.9),
            'feasibility_score': random.uniform(0.5, 0.85)
        }
        
    def triz_inventive_principles(self, problem: str, domain: str, seed: int, constraints: Any) -> Dict[str, Any]:
        """Theory of Inventive Problem Solving"""
        principles = ['Segmentation', 'Extraction', 'Local Quality', 'Asymmetry', 'Consolidation', 'Universality']
        principle = principles[seed % len(principles)]
        
        return {
            'title': f"TRIZ Principle: {principle}",
            'description': f"Solving contradictions in {domain} using {principle}.",
            'technique_aspect': principle,
            'novelty_score': random.uniform(0.7, 0.95),
            'feasibility_score': random.uniform(0.4, 0.8)
        }
        
    def six_thinking_hats(self, problem: str, domain: str, seed: int, constraints: Any) -> Dict[str, Any]:
        """De Bono's Six Thinking Hats"""
        hats = ['White (Data)', 'Red (Emotion)', 'Black (Caution)', 'Yellow (Optimism)', 'Green (Creativity)', 'Blue (Process)']
        hat = hats[seed % len(hats)]
        
        return {
            'title': f"{hat} perspective",
            'description': f"Analyzing {problem[:20]} from the {hat} standpoint.",
            'technique_aspect': hat,
            'novelty_score': random.uniform(0.5, 0.8),
            'feasibility_score': random.uniform(0.6, 0.9)
        }
        
    def first_principles_reasoning(self, problem: str, domain: str, seed: int, constraints: Any) -> Dict[str, Any]:
        """Deconstruct to fundamental truths and build up"""
        
        return {
            'title': f"Fundamental reconstruction {seed+1}",
            'description': f"Breaking down assumptions in {domain} to fundamental physics/logic.",
            'technique_aspect': 'Deconstruction',
            'novelty_score': random.uniform(0.8, 0.99),
            'feasibility_score': random.uniform(0.3, 0.7)
        }
        
    def biomimicry_mapping(self, problem: str, domain: str, seed: int, constraints: Any) -> Dict[str, Any]:
        """Map engineering/design problems to biological solutions"""
        biological_systems = ['Mycelium networks', 'Swarm intelligence', 'Photosynthesis', 'Lotus effect', 'Gecko adhesion']
        system = biological_systems[seed % len(biological_systems)]
        
        return {
            'title': f"Bio-inspired: {system}",
            'description': f"Applying principles from {system} to {domain} challenges.",
            'technique_aspect': system,
            'novelty_score': random.uniform(0.75, 0.95),
            'feasibility_score': random.uniform(0.4, 0.75)
        }
        
    def rank_ideas(self, ideas: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Rank ideas based on a combined score of novelty and feasibility"""
        for idea in ideas:
            # Calculate composite score: 60% novelty, 40% feasibility
            idea['composite_score'] = (idea['novelty_score'] * 0.6) + (idea['feasibility_score'] * 0.4)
            
        return sorted(ideas, key=lambda x: x['composite_score'], reverse=True)


class CrossDomainCreativeIntegrator:
    """Integrates creativity across multiple domains for breakthrough innovations"""
    
    def __init__(self):
        pass
        
    async def generate_cross_domain_synthesis(
        self,
        session: Session,
        agent_id: str,
        primary_domain: str,
        secondary_domains: List[str],
        synthesis_goal: str
    ) -> Dict[str, Any]:
        """Synthesize concepts from multiple domains to create novel outputs"""
        
        # Verify agent has capabilities in these domains
        capabilities = session.exec(
            select(CreativeCapability).where(
                and_(
                    CreativeCapability.agent_id == agent_id,
                    CreativeCapability.creative_domain.in_([primary_domain] + secondary_domains)
                )
            )
        ).all()
        
        found_domains = [cap.creative_domain for cap in capabilities]
        if primary_domain not in found_domains:
            raise ValueError(f"Agent lacks primary creative domain: {primary_domain}")
            
        # Determine synthesis approach based on available capabilities
        synergy_potential = len(found_domains) * 0.2
        
        # Simulate synthesis process
        await asyncio.sleep(0.8)
        
        synthesis_result = {
            'goal': synthesis_goal,
            'primary_framework': primary_domain,
            'integrated_perspectives': secondary_domains,
            'synthesis_output': f"Novel integration of {primary_domain} principles with mechanisms from {', '.join(secondary_domains)}",
            'synergy_score': min(0.95, 0.4 + synergy_potential + random.uniform(0, 0.2)),
            'innovation_level': 'disruptive' if synergy_potential > 0.5 else 'incremental',
            'suggested_applications': [
                f"Cross-functional application in {primary_domain}",
                f"Novel methodology for {secondary_domains[0] if secondary_domains else 'general use'}"
            ]
        }
        
        # Update cross-domain transfer metrics for involved capabilities
        for cap in capabilities:
            cap.cross_domain_transfer = min(1.0, cap.cross_domain_transfer + 0.05)
            session.add(cap)
            
        session.commit()
        
        return synthesis_result
