package com.phonetousb

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController
import com.phonetousb.ui.screens.*
import com.phonetousb.ui.theme.DarkBackground

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val app = application as PhoneToUSBApplication

        setContent {
            MaterialTheme {
                Surface(
                    modifier = Modifier.fillMaxSize(),
                    color = DarkBackground
                ) {
                    val navController = rememberNavController()
                    val selectedReceiver by app.receiverRepository.selectedReceiver.collectAsState()

                    NavHost(navController = navController, startDestination = "home") {
                        composable("home") {
                            HomeScreen(
                                receiverRepo = app.receiverRepository,
                                client = app.signalingClient,
                                onNavigateToBrowser = { navController.navigate("browser") },
                                onNavigateToPairing = { navController.navigate("pairing") },
                                onNavigateToDevices = { navController.navigate("devices") },
                                onNavigateToTransfers = { navController.navigate("transfers") },
                                onNavigateToUpdates = { navController.navigate("updates") },
                                onNavigateToSettings = { navController.navigate("settings") }
                            )
                        }

                        composable("browser") {
                            UsbBrowserScreen(
                                client = app.signalingClient,
                                selectedReceiver = selectedReceiver,
                                onNavigateBack = { navController.popBackStack() }
                            )
                        }

                        composable("pairing") {
                            PairingScreen(
                                client = app.signalingClient,
                                receiverRepo = app.receiverRepository,
                                onPairingSuccess = {
                                    navController.popBackStack()
                                    navController.navigate("browser")
                                },
                                onNavigateBack = { navController.popBackStack() }
                            )
                        }

                        composable("devices") {
                            DevicesScreen(
                                receiverRepo = app.receiverRepository,
                                onNavigateBack = { navController.popBackStack() }
                            )
                        }

                        composable("transfers") {
                            TransfersScreen(
                                transferRepo = app.transferRepository,
                                onNavigateBack = { navController.popBackStack() }
                            )
                        }

                        composable("updates") {
                            UpdatesScreen(
                                updateManager = app.updateManager,
                                onNavigateBack = { navController.popBackStack() }
                            )
                        }

                        composable("settings") {
                            SettingsScreen(
                                client = app.signalingClient,
                                onNavigateBack = { navController.popBackStack() }
                            )
                        }
                    }
                }
            }
        }
    }
}
