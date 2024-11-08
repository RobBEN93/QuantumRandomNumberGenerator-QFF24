
# QuantumRandomNumberGenerator

This project provides a *quantum-based random number generator* (*QRNG*) using **Qiskit** and simulated **IBM’s quantum backends**. The *QRNG* leverages the inherent probabilistic nature of quantum states to produce high-quality random numbers.

For this we construct quantum circuits and apply Hadamard gates to all qubits, generating an uniform superposition of all possible binary string combinations, then measuring.

Given any number of possible outcomes, the *QRNG* finds the required number of qubits for representing binary strings, namely `num_qubits = math.ceil(math.log2(num_possible_outcomes))`. However we want to run circuits of at most 10 qubits, so if this number is greater than 10, we make use of `quotient, remainder = divmod(num_qubits, 10)` and run the 10 circuit `quotient` number of times, and then an additional "remainder" circuit, with `remainder` number of qubits. We then run these circuits independently a number of times (default is `num_shots = 1024`) and then form larger strings by combining the outputs and multiplying the probabilities given by the counts.

**This repo has been submitted for the Qiskit Fall Fest Hackathon at CDMX, 2024.**
## Features
- **Quantum Randomness**: Generates random numbers using quantum superposition and measurement.
- **Large Numbers**: The program is designed with circuit runs of at most 10 qubits, so we can generate  large numbers. However, larger numbers require more RAM and processing time. 
- **Error Mitigation**: Incorporates measurement error mitigation to improve the reliability of results and an *optional custom gate error mitigation*. Measurement error mitigation is managed through the [M3 library](https://qiskit.github.io/qiskit-addon-mthree/).
- **Customizable Backend**: Supports both IBM quantum backends and Aer simulator with noise modeling.

## Requirements
- Python 3.8+
- Packages: `Qiskit`
`qiskit-aer`
`qiskit-ibm-runtime`
`mthree`

- You’ll also need an IBM Quantum Experience API token to access IBM’s quantum backends.

## Installation

1. Clone this repository:

```bash
git clone https://github.com/RobBEN93/QuantumRandomNumberGenerator-QFF24.git
cd QuantumRandomNumberGenerator
```

2. Install the required Python packages:

```bash
pip install qiskit qiskit-aer qiskit-ibm-runtime mthree
```

3. [Obtain an IBMQ API token](https://www.ibm.com/quantum).

## Usage

#### Initialization

Initialize the generator with the desired number of outcomes and your IBMQ Token:

```python
from qrng import QuantumRandomNumberGenerator

qrng = QuantumRandomNumberGenerator(num_possible_outcomes=10, api_token="YOUR-IBMQ-TOKEN", backend = 'ibm_sherbrooke')
```
#### Methods

`available_backends()`: Lists available IBM quantum backends accessible with the user’s account.

`fast_random_number()`: Generates a random number without applying gate error mitigation for faster results.

`gate_error_mit_random_number()`: Generates a random number with gate error mitigation to improve accuracy.

## Error Mitigation

**Measurement error mitigation**: This is managed through the [M3 library](https://qiskit.github.io/qiskit-addon-mthree/), which adjusts the output quasi-probability distribution to correct for errors induced in measurement. This improves result fidelity, especially useful when operating on real quantum backends.

**Gate/channel error mitigation**: Given that gates and channels have errors, we don't want a single gate acting over a single qubit to bias the result. Each run of the circuit produces (by default) `num_shots = 1024`. We then perform multiple of these runs, but we perform a number, dependent on the `mitigation_level` of permutations on the counts, spreading the errors of gates over different qubit positions. We are "simulating" that we change the gates over different qubits so that the errors spread outs.

The `mitigation_level` can be a float between 0 and 1. 1 introduces as many random permutations of the counts as the number of qubits, while 0.5 would introduce half as many permutations.

Note that all permutations might be considered but this is an $O(n!)$ problem, so we are only generating at most num_qubits permutations

Also note that this procedure can introduce high complexity so it might only be advantageous where gate and channel errors are very high and time isn't a big constraint.

##### Example: Generate a Random Number
```python
# Generate a fast random number
random_number = qrng.fast_random_number()
print(f"Fast Quantum Random Number: {random_number}")

# Generate a random number with error mitigation
mitigated_random_number = qrng.gate_error_mit_random_number(mitigation_level = 0.5)
print(f"Error-Mitigation Quantum Random Number: {mitigated_random_number}")
```

## Class Structure

`QuantumRandomNumberGenerator`
- `__init__()`: Sets up the quantum circuit, backend, and error mitigation.
- `_run_and_correct()`: Runs the quantum circuit and applies M3 error mitigation.
- `_gen_flattened_quasis_dict()`: Accumulates error-mitigated quasi-probabilities with random permutation for reliability.
- `_merge_counts()`: Merges multiple quasi-distribution counts from different circuit runs.
- `_select_number()`: Selects the highest quasi-probability outcome from the distribution.
- `fast_random_number()`: Quickly generates a random number without gate error mitigation.
- `gate_error_mit_random_number()`: Generates a random number with custom gate error mitigation.

Please let me know if you’d like more details!