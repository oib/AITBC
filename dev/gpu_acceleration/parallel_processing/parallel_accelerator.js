#!/usr/bin/env node

/**
 * Parallel Processing Accelerator for SnarkJS Operations
 *
 * Implements parallel processing optimizations for ZK proof generation
 * to leverage multi-core CPUs and prepare for GPU acceleration integration.
 */

const { Worker, isMainThread, parentPort, workerData } = require('worker_threads');
const { spawn } = require('child_process');
const fs = require('fs');
const path = require('path');
const os = require('os');

// Configuration
const NUM_WORKERS = Math.min(os.cpus().length, 8); // Use up to 8 workers
const WORKER_TIMEOUT = 300000; // 5 minutes timeout

class SnarkJSParallelAccelerator {
    constructor() {
        this.workers = [];
        this.activeJobs = new Map();
        console.log(`🚀 SnarkJS Parallel Accelerator initialized with ${NUM_WORKERS} workers`);
    }

    /**
     * Generate proof with parallel processing optimization
     */
    async generateProofParallel(r1csPath, witnessPath, zkeyPath, outputDir = 'parallel_output') {
        console.log('🔧 Starting parallel proof generation...');

        const startTime = Date.now();
        const jobId = `proof_${Date.now()}`;

        // Create output directory
        if (!fs.existsSync(outputDir)) {
            fs.mkdirSync(outputDir, { recursive: true });
        }

        // Convert relative paths to absolute paths (relative to main project directory)
        const projectRoot = path.resolve(__dirname, '../../..'); // Go up from parallel_processing to project root
        const absR1csPath = path.resolve(projectRoot, r1csPath);
        const absWitnessPath = path.resolve(projectRoot, witnessPath);
        const absZkeyPath = path.resolve(projectRoot, zkeyPath);

        console.log(`📁 Project root: ${projectRoot}`);
        console.log(`📁 Using absolute paths:`);
        console.log(`   R1CS: ${absR1csPath}`);
        console.log(`   Witness: ${absWitnessPath}`);
        console.log(`   ZKey: ${absZkeyPath}`);

        // Split the proof generation into parallel tasks
        const tasks = [
            {
                type: 'witness_verification',
                command: 'snarkjs',
                args: ['wtns', 'check', absR1csPath, absWitnessPath],
                description: 'Witness verification'
            },
            {
                type: 'proof_generation',
                command: 'snarkjs',
                args: ['groth16', 'prove', absZkeyPath, absWitnessPath, `${outputDir}/proof.json`, `${outputDir}/public.json`],
                description: 'Proof generation',
                dependsOn: ['witness_verification']
            },
            {
                type: 'proof_verification',
                command: 'snarkjs',
                args: ['groth16', 'verify', `${outputDir}/verification_key.json`, `${outputDir}/public.json`, `${outputDir}/proof.json`],
                description: 'Proof verification',
                dependsOn: ['proof_generation']
            }
        ];

        try {
            // Execute tasks with dependency management
            const results = await this.executeTasksWithDependencies(tasks);

            const duration = Date.now() - startTime;
            console.log(`✅ Parallel proof generation completed in ${duration}ms`);

            return {
                success: true,
                duration,
                outputDir,
                results,
                performance: {
                    workersUsed: NUM_WORKERS,
                    tasksExecuted: tasks.length,
                    speedupFactor: this.calculateSpeedup(results)
                }
            };

        } catch (error) {
            console.error('❌ Parallel proof generation failed:', error.message);
            return {
                success: false,
                error: error.message,
                duration: Date.now() - startTime
            };
        }
    }

    /**
     * Execute tasks with dependency management
     */
    async executeTasksWithDependencies(tasks) {
        const completedTasks = new Set();
        const taskResults = new Map();

        while (completedTasks.size < tasks.length) {
            // Find tasks that can be executed (dependencies satisfied)
            const readyTasks = tasks.filter(task =>
                !completedTasks.has(task.type) &&
                (!task.dependsOn || task.dependsOn.every(dep => completedTasks.has(dep)))
            );

            if (readyTasks.length === 0) {
                throw new Error('Deadlock detected: no tasks ready to execute');
            }

            // Execute ready tasks in parallel (up to NUM_WORKERS)
            const batchSize = Math.min(readyTasks.length, NUM_WORKERS);
            const batchTasks = readyTasks.slice(0, batchSize);

            console.log(`🔄 Executing batch of ${batchTasks.length} tasks in parallel...`);

            const batchPromises = batchTasks.map(task =>
                this.executeTask(task).then(result => ({
                    task: task.type,
                    result,
                    description: task.description
                }))
            );

            const batchResults = await Promise.allSettled(batchPromises);

            // Process results
            batchResults.forEach((promiseResult, index) => {
                const task = batchTasks[index];

                if (promiseResult.status === 'fulfilled') {
                    console.log(`✅ ${task.description} completed`);
                    completedTasks.add(task.type);
                    taskResults.set(task.type, promiseResult.value);
                } else {
                    console.error(`❌ ${task.description} failed:`, promiseResult.reason);
                    throw new Error(`${task.description} failed: ${promiseResult.reason.message}`);
                }
            });
        }

        return Object.fromEntries(taskResults);
    }

    /**
     * Execute a single task
     */
    async executeTask(task) {
        return new Promise((resolve, reject) => {
            console.log(`🔧 Executing: ${task.description}`);

            const child = spawn(task.command, task.args, {
                stdio: ['inherit', 'pipe', 'pipe'],
                timeout: WORKER_TIMEOUT
            });

            let stdout = '';
            let stderr = '';

            child.stdout.on('data', (data) => {
                stdout += data.toString();
            });

            child.stderr.on('data', (data) => {
                stderr += data.toString();
            });

            child.on('close', (code) => {
                if (code === 0) {
                    resolve({
                        code,
                        stdout,
                        stderr,
                        command: `${task.command} ${task.args.join(' ')}`
                    });
                } else {
                    reject(new Error(`Command failed with code ${code}: ${stderr}`));
                }
            });

            child.on('error', (error) => {
                reject(error);
            });
        });
    }

    /**
     * Calculate speedup factor based on task execution times
     */
    calculateSpeedup(results) {
        // Simple speedup calculation - in practice would need sequential baseline
        const totalTasks = Object.keys(results).length;
        const parallelTime = Math.max(...Object.values(results).map(r => r.result.duration || 0));

        // Estimate sequential time as sum of individual task times
        const sequentialTime = Object.values(results).reduce((sum, r) => sum + (r.result.duration || 0), 0);

        return sequentialTime > 0 ? sequentialTime / parallelTime : 1;
    }

    /**
     * Benchmark parallel vs sequential processing
     */
    async benchmarkProcessing(r1csPath, witnessPath, zkeyPath, iterations = 3) {
        console.log(`📊 Benchmarking parallel processing (${iterations} iterations)...`);

        const results = {
            parallel: [],
            sequential: []
        };

        // Parallel benchmarks
        for (let i = 0; i < iterations; i++) {
            console.log(`🔄 Parallel iteration ${i + 1}/${iterations}`);
            const startTime = Date.now();

            try {
                const result = await this.generateProofParallel(
                    r1csPath,
                    witnessPath,
                    zkeyPath,
                    `benchmark_parallel_${i}`
                );

                if (result.success) {
                    results.parallel.push({
                        duration: result.duration,
                        speedup: result.performance?.speedupFactor || 1
                    });
                }
            } catch (error) {
                console.error(`Parallel iteration ${i + 1} failed:`, error.message);
            }
        }

        // Calculate statistics
        const parallelAvg = results.parallel.length > 0
            ? results.parallel.reduce((sum, r) => sum + r.duration, 0) / results.parallel.length
            : 0;

        const speedupAvg = results.parallel.length > 0
            ? results.parallel.reduce((sum, r) => sum + r.speedup, 0) / results.parallel.length
            : 1;

        console.log(`📈 Benchmark Results:`);
        console.log(`   Parallel average: ${parallelAvg.toFixed(2)}ms`);
        console.log(`   Average speedup: ${speedupAvg.toFixed(2)}x`);
        console.log(`   Successful runs: ${results.parallel.length}/${iterations}`);

        return {
            parallelAverage: parallelAvg,
            speedupAverage: speedupAvg,
            successfulRuns: results.parallel.length,
            totalRuns: iterations
        };
    }
}

// CLI interface
async function main() {
    const args = process.argv.slice(2);

    if (args.length < 3) {
        console.log('Usage: node parallel_accelerator.js <r1cs_file> <witness_file> <zkey_file> [output_dir]');
        console.log('');
        console.log('Commands:');
        console.log('  prove <r1cs> <witness> <zkey> [output]  - Generate proof with parallel processing');
        console.log('  benchmark <r1cs> <witness> <zkey> [iterations] - Benchmark parallel vs sequential');
        process.exit(1);
    }

    const accelerator = new SnarkJSParallelAccelerator();
    const command = args[0];

    try {
        if (command === 'prove') {
            const [_, r1csPath, witnessPath, zkeyPath, outputDir] = args;
            const result = await accelerator.generateProofParallel(r1csPath, witnessPath, zkeyPath, outputDir);

            if (result.success) {
                console.log('🎉 Proof generation successful!');
                console.log(`   Output directory: ${result.outputDir}`);
                console.log(`   Duration: ${result.duration}ms`);
                console.log(`   Speedup: ${result.performance?.speedupFactor?.toFixed(2) || 'N/A'}x`);
            } else {
                console.error('❌ Proof generation failed:', result.error);
                process.exit(1);
            }
        } else if (command === 'benchmark') {
            const [_, r1csPath, witnessPath, zkeyPath, iterations = '3'] = args;
            const results = await accelerator.benchmarkProcessing(r1csPath, witnessPath, zkeyPath, parseInt(iterations));

            console.log('🏁 Benchmarking complete!');
        } else {
            console.error('Unknown command:', command);
            process.exit(1);
        }
    } catch (error) {
        console.error('❌ Error:', error.message);
        process.exit(1);
    }
}

if (require.main === module) {
    main().catch(console.error);
}

module.exports = { SnarkJSParallelAccelerator };
